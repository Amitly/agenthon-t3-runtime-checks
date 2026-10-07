"""Read-only resource evidence. No daemon/context/controller changes."""
import hashlib,json,os,pathlib,subprocess,threading,time
P=pathlib.Path
def read(p):
 try:return P(p).read_text().strip()
 except (FileNotFoundError,PermissionError):return 'unavailable'
def cmd(args):return subprocess.check_output(args,text=True)
class IdentityValidationError(AssertionError):
 def __init__(self,report):
  self.report=report
  super().__init__('Image identity failed: '+', '.join(report['failures']))
class ConfigComparisonError(AssertionError):
 def __init__(self,report):
  self.report=report
  super().__init__('Config comparison failed: '+', '.join(report['failures']))
_IDENTITY_VERIFIED=object()
class VerifiedIdentity:
 """Returned only after byte digests, ordered layers and platform all pass."""
 def __init__(self,config_bytes,report,token):
  if token is not _IDENTITY_VERIFIED:raise TypeError('Use verify_identity with original bytes')
  self._config_bytes=bytes(config_bytes);self.report=report
 @property
 def raw(self):return json.loads(self._config_bytes)
def typed_equal(a,b):
 if type(a) is not type(b):return False
 if isinstance(a,dict):return set(a)==set(b) and all(typed_equal(a[k],b[k]) for k in a)
 if isinstance(a,list):return len(a)==len(b) and all(typed_equal(x,y) for x,y in zip(a,b))
 return a==b
def verify_identity(manifest_bytes,config_bytes,expected,actual):
 """Bind retained original JSON bytes to the frozen reference and live inspect."""
 checks=[];report={'status':'STARTED','checks':checks,'failures':[],
  'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
  'config_sha256':hashlib.sha256(config_bytes).hexdigest(),
  'manifest_bytes':len(manifest_bytes),'config_bytes':len(config_bytes),
  'expected_ref':expected.get('ref'),'expected_id':expected.get('id')}
 def check(name,ok):checks.append({'check':name,'passed':bool(ok)})
 manifest={};raw={}
 for name,payload in [('manifest',manifest_bytes),('config',config_bytes)]:
  try:
   obj=json.loads(payload);check(name+'_JSON_object',type(obj) is dict)
   if type(obj) is dict:
    if name=='manifest':manifest=obj
    else:raw=obj
  except (ValueError,UnicodeError) as ex:
   check(name+'_JSON_object',False);report[name+'_parse_error']=type(ex).__name__+': '+str(ex)
 reference=expected.get('ref');digest=reference.rsplit('@',1)[-1] if type(reference) is str and '@' in reference else None
 check('manifest_digest_equals_frozen_ref',digest=='sha256:'+report['manifest_sha256'])
 check('manifest_schemaVersion',type(manifest.get('schemaVersion')) is int and manifest.get('schemaVersion')==2)
 descriptor=manifest.get('config') if type(manifest.get('config')) is dict else {}
 check('config_digest_equals_manifest',descriptor.get('digest')=='sha256:'+report['config_sha256'])
 check('config_size_equals_manifest',type(descriptor.get('size')) is int and descriptor.get('size')==len(config_bytes))
 check('config_digest_equals_frozen_ID','sha256:'+report['config_sha256']==expected.get('id'))
 rootfs=raw.get('rootfs') if type(raw.get('rootfs')) is dict else {}
 inspected_rootfs=actual.get('RootFS') if type(actual.get('RootFS')) is dict else {}
 check('raw_rootfs_type',rootfs.get('type')=='layers')
 check('raw_ordered_RootFS',typed_equal(rootfs.get('diff_ids'),expected.get('rootfs')))
 check('raw_platform',raw.get('os')=='linux' and raw.get('architecture')=='amd64')
 check('raw_Config_object',type(raw.get('config')) is dict)
 check('actual_ID',actual.get('Id')==expected.get('id'))
 check('actual_rootfs_type',inspected_rootfs.get('Type')=='layers')
 check('actual_ordered_RootFS',typed_equal(inspected_rootfs.get('Layers'),expected.get('rootfs')))
 check('actual_platform',actual.get('Os')=='linux' and actual.get('Architecture')=='amd64')
 check('actual_Config_object',type(actual.get('Config')) is dict)
 report['failures']=[c['check'] for c in checks if not c['passed']]
 report['status']='FAIL' if report['failures'] else 'PASS'
 if report['failures']:raise IdentityValidationError(report)
 return VerifiedIdentity(config_bytes,report,_IDENTITY_VERIFIED)
def _nested_differences(a,b,path):
 if typed_equal(a,b):return []
 if type(a) is dict and type(b) is dict:
  rows=[]
  for key in sorted(set(a)|set(b)):
   child=path+'/'+key
   if key in a and key in b:rows.extend(_nested_differences(a[key],b[key],child))
   else:rows.append({'path':child,'actual_present':key in a,'expected_present':key in b,'actual_type':type(a[key]).__name__ if key in a else 'missing','expected_type':type(b[key]).__name__ if key in b else 'missing','actual':a.get(key),'expected':b.get(key)})
  return rows
 if type(a) is list and type(b) is list and len(a)==len(b):
  return [row for i,(x,y) in enumerate(zip(a,b)) for row in _nested_differences(x,y,path+'/'+str(i))]
 return [{'path':path,'actual_type':type(a).__name__,'expected_type':type(b).__name__,'actual':a,'expected':b}]
def config_comparison_report(actual,expected,identity=None):
 """Collect every difference before the caller persists the report and raises."""
 report={'status':'STARTED','actual':actual,'expected':expected,'differences':[],'failures':[]}
 if type(actual) is not dict or type(expected) is not dict:
  report.update(status='FAIL',failures=['Config must be an object']);return report
 bound=type(identity) is VerifiedIdentity and identity.report.get('status')=='PASS'
 raw=identity.raw['config'] if bound else {}
 report['raw_identity_binding']=identity.report if bound else None
 defaults={'Hostname':'','Domainname':'','User':'','AttachStdin':False,'AttachStdout':False,'AttachStderr':False,'Tty':False,'OpenStdin':False,'StdinOnce':False,'Entrypoint':None,'OnBuild':None,'Volumes':None}
 for k in sorted(set(actual)|set(expected)|{'Image'}):
  ap=k in actual;ep=k in expected;av=actual.get(k);ev=expected.get(k)
  row={'field':k,'actual_present':ap,'expected_present':ep,'actual_type':type(av).__name__ if ap else 'missing','expected_type':type(ev).__name__ if ep else 'missing','actual':av,'expected':ev}
  same=ap==ep and (not ap or typed_equal(av,ev))
  if k=='Image':
   rp='Image' in raw;rv=raw.get('Image')
   raw_valid=not rp or type(rv) is str
   def allowed(present,value):return not present or (type(value) is str and (value=='' or (bound and rp and type(rv) is str and rv!='' and value==rv)))
   ok=raw_valid and allowed(ap,av) and allowed(ep,ev)
   row.update(rule='Image: missing, strict empty string, or exact nonempty value from digest-bound raw config',raw_present=rp,raw_type=type(rv).__name__ if rp else 'missing',raw_value=rv)
  elif ap and ep:ok=typed_equal(av,ev);row['rule']='strict recursive typed equality'
  else:
   present=av if ap else ev;ok=k in defaults and typed_equal(present,defaults[k]);row['rule']='fixed typed-Config default only'
  row['passed']=ok
  if not same and ap and ep:row['nested_differences']=_nested_differences(av,ev,'/'+k)
  if not same or not ok:report['differences'].append(row)
  if not ok:report['failures'].append(k)
 report['status']='FAIL' if report['failures'] else 'PASS'
 return report
def compare_config(actual,expected,identity=None):
 report=config_comparison_report(actual,expected,identity)
 if report['status']!='PASS':raise ConfigComparisonError(report)
 return report['differences']
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
