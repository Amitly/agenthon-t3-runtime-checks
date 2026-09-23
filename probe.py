"""Non-simulation probe, executed inside the exact frozen image."""
import errno,hashlib,json,os,pathlib,platform,resource,sys,time
P=pathlib.Path
def read(p):
 try:return P(p).read_text().strip()
 except (FileNotFoundError,PermissionError):return 'unavailable'
def denied(p):
 try:P(p).write_text('probe');return None
 except OSError as e:return e.errno
from abides_markets import order_book,price_level
import abides_markets._native_book as native
assert native.__file__.endswith('.so')
assert price_level.PriceLevel.__module__=='abides_markets._native_book'
with open(native.__file__,'rb') as f:native_sha=hashlib.sha256(f.read()).hexdigest()
assert native_sha=='0887a383cceadbc95d09ba1f9d50962f82599a4f2ba31eae54680468e9d8b2d3'
data={'uid':os.getuid(),'gid':os.getgid(),'cwd':os.getcwd(),'python':sys.version,'machine':platform.machine(),
 'dontwritebytecode':os.getenv('PYTHONDONTWRITEBYTECODE'),'extension_file':native.__file__,'extension_sha256':native_sha,
 'cpus_allowed':sorted(os.sched_getaffinity(0)),'self_status':read('/proc/self/status'),'self_cgroup':read('/proc/self/cgroup'),
 'mountinfo':read('/proc/self/mountinfo'),'tmp_bytes':os.statvfs('/tmp').f_blocks*os.statvfs('/tmp').f_frsize,
 'limits':{k:resource.getrlimit(getattr(resource,k)) for k in ['RLIMIT_NOFILE','RLIMIT_NPROC','RLIMIT_FSIZE']},
 'cgroup':{n:read('/sys/fs/cgroup/'+n) for n in ['cpu.max','cpu.stat','memory.max','memory.swap.max','pids.max','cpuset.cpus.effective']},
 'network_interfaces':os.listdir('/sys/class/net'),'root_write_errno':denied('/rootfs-probe'),'input_write_errno':denied('/input/probe.py')}
assert data['uid']==data['gid']==65534 and data['cwd']=='/tmp' and platform.machine()=='x86_64'
assert sys.version_info[:3]==(3,11,16) and data['dontwritebytecode']=='1'
assert data['root_write_errno']==data['input_write_errno']==errno.EROFS
assert data['tmp_bytes']==67108864 and data['network_interfaces']==['lo']
P('/output/probe.json').write_text(json.dumps(data,indent=2)+'\n')
# Stay alive briefly for the host to read actual parent cgroups; this is not a simulation.
deadline=time.monotonic()+40
while not P('/output/finish').exists() and time.monotonic()<deadline:time.sleep(.05)
assert P('/output/finish').exists(),'host did not complete parent-cgroup readback'
