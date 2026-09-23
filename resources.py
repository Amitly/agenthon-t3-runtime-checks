"""Read-only resource evidence. No daemon/context/controller changes."""
import json,os,pathlib,subprocess,threading,time
P=pathlib.Path
def read(p):
 try:return P(p).read_text().strip()
 except (FileNotFoundError,PermissionError):return 'unavailable'
def cmd(args):return subprocess.check_output(args,text=True)
def compare_config(actual,expected):
 # Fixed Moby typed-Config zero values; raw image ID/rootfs remain exact.
 # Only absent versus the named default is accepted, never an unknown field.
 defaults={'Hostname':'','Domainname':'','Image':'','User':'','AttachStdin':False,'AttachStdout':False,'AttachStderr':False,'Tty':False,'OpenStdin':False,'StdinOnce':False,'Entrypoint':None,'OnBuild':None,'Volumes':None}
 differences=[]
 for k in set(actual)|set(expected):
  if k in actual and k in expected:
   assert type(actual[k]) is type(expected[k]) and actual[k]==expected[k],k
  else:
   present=actual[k] if k in actual else expected[k]
   assert k in defaults and type(present) is type(defaults[k]) and present==defaults[k],k
   differences.append({'field':k,'actual_present':k in actual,'expected_present':k in expected,'value':present,'rule':'fixed typed-Config default'})
 return differences
def flags():return ['--pull=never','--platform=linux/amd64','--runtime=runc','--network=none','--cpus=4','--memory=16g','--memory-swap=16g','--user=65534:65534','--cap-drop=ALL','--security-opt=no-new-privileges','--read-only','--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864,mode=1777','--pids-limit=256','--ulimit=nproc=256:256','--ulimit=nofile=1024:1024','--ulimit=fsize=67108864:67108864']
def memory_guard(peak):
 mem={k:int(v.strip().split()[0])*1024 for k,v in (line.split(':',1) for line in P('/proc/meminfo').read_text().splitlines())}
 assert mem['MemAvailable']>=8*1024**3 and mem['MemAvailable']>peak*1.5+2*1024**3,mem
 return {'MemTotal':mem['MemTotal'],'MemAvailable':mem['MemAvailable'],'historical_peak':peak,'guard':'available>=8GiB and >1.5*selected historical peak+2GiB, no future guarantee'}
def cgroups(pid):
 rows=[];text=read(f'/proc/{pid}/cgroup')
 for line in text.splitlines():
  parts=line.split(':',2)
  if len(parts)!=3:continue
  _,controllers,path=parts
  root=P('/sys/fs/cgroup') if controllers=='' else P('/sys/fs/cgroup')/controllers
  p=root/path.lstrip('/')
  # Docker cgroupv1 may expose a combined cpu,cpuacct controller path.
  if not p.exists():continue
  while True:
   names=['cpu.max','cpu.stat','cpu.cfs_quota_us','cpu.cfs_period_us','memory.max','memory.swap.max','memory.limit_in_bytes','memory.memsw.limit_in_bytes','pids.max','cpuset.cpus.effective','cpuset.cpus']
   row={'path':str(p),'controllers':controllers,**{n:read(p/n) for n in names}};rows.append(row)
   if p==root:break
   p=p.parent
 return {'process_cgroup':text,'process_status':read(f'/proc/{pid}/status'),'ancestors':rows}
def check_cgroups(e):
 rows=e['ancestors'];cpu=[r for r in rows if r['cpu.max']!='unavailable'];mem=[r for r in rows if r['memory.max']!='unavailable']
 if cpu:
  assert cpu[0]['cpu.max']=='400000 100000',cpu
  assert mem[0]['memory.max']=='17179869184' and mem[0]['memory.swap.max']=='0',mem
  for r in cpu:
   quota,period=r['cpu.max'].split();assert quota=='max' or int(quota)/int(period)>=4
 else:
  cpu=[r for r in rows if r['cpu.cfs_quota_us']!='unavailable'];mem=[r for r in rows if r['memory.limit_in_bytes']!='unavailable']
  assert cpu and cpu[0]['cpu.cfs_quota_us']=='400000' and cpu[0]['cpu.cfs_period_us']=='100000'
  assert mem and mem[0]['memory.limit_in_bytes']=='17179869184' and mem[0]['memory.memsw.limit_in_bytes']=='17179869184'
  for r in cpu:assert int(r['cpu.cfs_quota_us'])<0 or int(r['cpu.cfs_quota_us'])/int(r['cpu.cfs_period_us'])>=4
 assert any(r['pids.max']=='256' for r in rows)
 assert 'Cpus_allowed_list:' in e['process_status']
 for r in mem:
  value=r['memory.max'] if r['memory.max']!='unavailable' else r['memory.limit_in_bytes']
  assert value=='max' or int(value)>=17179869184
 return True
def check_inspect(ins,image):
 h=ins['HostConfig'];mounts={x['Destination']:x for x in ins['Mounts']};u={x['Name']:(x['Soft'],x['Hard']) for x in h['Ulimits']}
 assert ins['Image']==image and ins['Config']['WorkingDir']=='/tmp' and ins['Config']['User']=='65534:65534'
 assert h['NanoCpus']==4000000000 and not h['CpusetCpus'] and h['CpuShares']==0
 assert h['Memory']==h['MemorySwap']==17179869184 and h['PidsLimit']==256
 assert h['ReadonlyRootfs'] and h['NetworkMode']=='none' and 'ALL' in h['CapDrop'] and 'no-new-privileges' in h['SecurityOpt']
 assert all(s in h['Tmpfs']['/tmp'].split(',') for s in ['rw','noexec','nosuid','nodev','size=67108864','mode=1777'])
 assert u=={'nofile':(1024,1024),'nproc':(256,256),'fsize':(67108864,67108864)}
 assert set(mounts)=={'/input','/output'} and not mounts['/input']['RW'] and mounts['/output']['RW']
 assert not ins['State']['OOMKilled']
class Observe:
 """Passive cgroup readback while official timer runs; identical on F/I, no profiler."""
 def __init__(self,cidfile):self.cidfile=cidfile;self.stop=threading.Event();self.first=None;self.last=None;self.error=None
 def work(self):
  try:
   pid=None
   while not self.stop.wait(.03):
    if pid is None and self.cidfile.exists():
     cid=self.cidfile.read_text().strip()
     if not cid:continue
     raw=subprocess.run(['docker','inspect','--format={{.State.Pid}}',cid],capture_output=True,text=True)
     if raw.returncode==0 and raw.stdout.strip().isdigit() and int(raw.stdout)>0:pid=int(raw.stdout)
    if pid:
     e=cgroups(pid)
     if e['ancestors']:
      if self.first is None:self.first=e
      self.last=e
  except Exception as ex:self.error=type(ex).__name__+': '+str(ex)
 def __enter__(self):self.thread=threading.Thread(target=self.work);self.thread.start();return self
 def __exit__(self,*exc):self.stop.set();self.thread.join()
