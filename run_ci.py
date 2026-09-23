"""Single serial CFS spot check. Frozen images, official timer/staging/scorer."""
import csv,dataclasses,datetime,enum,hashlib,importlib.metadata,json,os,pathlib,platform,shutil,statistics,subprocess,sys,time,tomllib,traceback
P=pathlib.Path;ROOT=P(__file__).resolve().parent;O=ROOT/'evidence';N=ROOT/'track-src';C=json.loads((ROOT/'frozen.json').read_text())
sys.path.insert(0,str(N))
import checks,resources
from throughput.run_unit import _stage_input,_host_n_events,_reported_n_events
from throughput.timer import timed_container_run
from qfbench2_common.sanitize import materialize_tree,verify_destination
from qfbench2_common.contracts.artifact_tree import TreeLimits
from qfbench2_track_simulation.limits import allowed_paths_for
from qfbench2_track_simulation import SCORER_VERSION
ledger=[];pairs=[];probes=[]
def enc(x):
 if isinstance(x,enum.Enum):return x.value
 if isinstance(x,P):return str(x)
 if dataclasses.is_dataclass(x):return dataclasses.asdict(x)
 raise TypeError(type(x).__name__)
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,indent=2,default=enc,allow_nan=False)+'\n');tmp.replace(p)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(a,timeout=120):return subprocess.run(a,capture_output=True,text=True,timeout=timeout)
def inspect(name):return json.loads(subprocess.check_output(['docker','inspect',name]))[0]
def reconcile():save(O/'calls.json',{'budget':26,'attempts':len(ledger),'passed':sum(x['state']=='PASS' for x in ledger),'probes':probes,'records':ledger,'builds':0,'uploads':0,'profiler_calls':0})
def schedule():
 rows=[{'stage':'initial','unit':u,'version':'I','pair':0,'order':'I'} for u in C['units'][:2]]
 for u in C['units'][2:]:
  rows.extend({'stage':'warmup','unit':u,'version':v,'pair':0,'order':'FI'} for v in 'FI')
  for k,order in enumerate(['FI','IF'],1):rows.extend({'stage':'formal','unit':u,'version':v,'pair':k,'order':order} for v in order)
 assert len(rows)==26
 return rows
def dirs(base):
 base.mkdir(parents=True,exist_ok=False);i=base/'input';o=base/'output';i.mkdir();o.mkdir();os.chown(o,65534,65534);o.chmod(0o755);return i,o
def node():
 info=json.loads(subprocess.check_output(['docker','info','--format={{json .}}']))
 return {'engine_id':info['ID'],'name':info['Name'],'os':info['OSType'],'architecture':info['Architecture'],'cgroup_version':info['CgroupVersion'],'endpoint':os.environ['DOCKER_HOST']}
def preflight():
 assert os.environ.get('GITHUB_REPOSITORY')=='Amitly/agenthon-t3-runtime-checks'
 assert os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1'
 assert platform.machine()=='x86_64' and sys.version_info[:3]==(3,13,15)
 assert importlib.metadata.version('qfbench2-common')=='2.4.2' and SCORER_VERSION=='3.1.0'
 os.environ.pop('DOCKER_CONTEXT',None);os.environ['DOCKER_HOST']='unix:///var/run/docker.sock'
 empty=ROOT/'empty-docker-config';empty.mkdir(mode=0o700,exist_ok=False);os.environ['DOCKER_CONFIG']=str(empty)
 assert not list(empty.iterdir());engine=node();assert engine['os']=='linux' and engine['architecture'] in ['x86_64','amd64']
 assert not subprocess.check_output(['docker','ps','-q'],text=True).strip()
 save(O/'node.json',{'docker':engine,'uname':platform.uname()._asdict(),'cpu_topology':run(['lscpu','-e']).stdout,'online':resources.read('/sys/devices/system/cpu/online'),'allowed_cpus':sorted(os.sched_getaffinity(0)),'memory':resources.memory_guard(C['maximum_historical_peak_bytes']),'python':sys.version,'dependencies':{x.metadata['Name']:x.version for x in importlib.metadata.distributions()},'timing':'official fixed local timer, host_measured; no official hardware equivalence'})
 for v in ['F','I']:
  before=subprocess.check_output(['docker','image','ls','--no-trunc'],text=True);p=run(['docker','pull','--platform=linux/amd64',C[v]['ref']],600)
  save(O/f'pull-{v}.json',{'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'before_images':before,'credentials':'fresh empty CLI config','ref':C[v]['ref']});assert p.returncode==0
  actual=inspect(C[v]['ref']);save(O/f'image-{v}.json',actual)
  assert actual['Id']==C[v]['id'] and actual['RootFS']['Layers']==C[v]['rootfs']
  differences=resources.compare_config(actual['Config'],C[v]['config']);save(O/f'config-representation-{v}.json',differences)
  assert actual['Architecture']=='amd64' and actual['Os']=='linux' and actual['Config']['WorkingDir']=='/tmp'
 base=O/'resource-probe';i,o=dirs(base);shutil.copy2(ROOT/'probe.py',i/'probe.py');(i/'probe.py').chmod(0o644)
 name='t3-core004c-resource';args=['docker','run','--name',name,*resources.flags(),'-v',str(i)+':/input:ro','-v',str(o)+':/output',C['I']['ref'],'python','/input/probe.py']
 probes.append({'index':1,'kind':'resource-native-import','state':'STARTED'});reconcile();save(base/'launch.json',args)
 with (base/'stdout.log').open('wb') as stdout,(base/'stderr.log').open('wb') as stderr:
  proc=subprocess.Popen(args,stdout=stdout,stderr=stderr);deadline=time.monotonic()+45
  while not (o/'probe.json').exists() and proc.poll() is None and time.monotonic()<deadline:time.sleep(.1)
  try:
   assert (o/'probe.json').exists(),'probe failed before ready; inspect stderr'
   ins=inspect(name);save(base/'inspect-running.json',ins);resources.check_inspect(ins,C['I']['id'])
   cg=resources.cgroups(ins['State']['Pid']);save(base/'cgroups.json',cg);resources.check_cgroups(cg)
   inside=json.loads((o/'probe.json').read_text());assert inside['extension_sha256']==C['I']['extension_sha256'];assert len(inside['cpus_allowed'])>=4
   assert set(inside['cpus_allowed'])<=set(os.sched_getaffinity(0))
   (o/'finish').write_text('host readback complete\n');assert proc.wait(timeout=10)==0
   save(base/'inspect-exited.json',inspect(name));probes[-1]['state']='PASS';reconcile()
   subprocess.run(['docker','rm',name],check=True,capture_output=True)
  except BaseException:
   probes[-1]['state']='FAIL';reconcile();(o/'finish').write_text('host failed\n');proc.wait(timeout=45);raise
 return engine
def one(item,engine):
 assert len(ledger)<26 and all(x['state']=='PASS' for x in ledger);assert node()==engine
 memory=resources.memory_guard(C['maximum_historical_peak_bytes']);idx=len(ledger)+1;v=item['version'];name=item['unit'];unit=N/'units'/name;card=tomllib.loads((unit/'card.toml').read_text());batch=(unit/'batch.json').exists()
 base=O/'simulations'/f'{idx:02d}-{item["stage"]}-{name}-{v}';i,o=dirs(base);_stage_input(unit,i,batch)
 for path in i.rglob('*'):path.chmod(0o755 if path.is_dir() else 0o644)
 assert all(p.name=='scenario.json' or batch for p in i.rglob('*') if p.is_file())
 verbs=['simulate-batch','--batch-dir','/input/scenarios','--out-dir','/output'] if batch else ['simulate','--config','/input/scenario.json','--out','/output/trace.parquet']
 cid=base/'container.cid';cname='t3-core004c-'+str(idx);args=['docker','run','--name',cname,'--cidfile',str(cid),*resources.flags(),'-v',str(i)+':/input:ro','-v',str(o)+':/output',C[v]['ref'],*verbs]
 rec={**item,'index':idx,'state':'STARTED','path':str(base.relative_to(O)),'image_id':C[v]['id'],'image':C[v]['ref'],'cpu_mode':'CFS_4','instrumented':False,'rankable':False,'family':card['task']['scenario_family'],'start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'memory_before':memory}
 ledger.append(rec);reconcile();save(base/'launch.json',args);print('START',idx,v,name,flush=True)
 try:
  with resources.Observe(cid) as obs:proc,wall,gpu,mem=timed_container_run(args,cidfile=cid,gpus=None,timeout_sec=1800)
  (base/'stdout.log').write_bytes(proc.stdout);(base/'stderr.log').write_bytes(proc.stderr)
  rec.update(returncode=proc.returncode,host_wall_sec=wall,host_peak_memory_bytes=mem,host_memory_source='fixed timer cgroup sampler; not process RSS')
  save(base/'cgroups.json',{'first':obs.first,'last':obs.last,'error':obs.error});assert obs.first and not obs.error;resources.check_cgroups(obs.first)
  actual=inspect(cname);save(base/'inspect.json',actual);resources.check_inspect(actual,C[v]['id']);assert proc.returncode==0
  san=materialize_tree(o,base/'sanitized-output',limits=TreeLimits(max_depth=2,max_file_bytes=67108864,max_total_bytes=67108864),allowed_paths=allowed_paths_for(unit));errors=verify_destination(base/'sanitized-output',san.files);save(base/'sanitizer.json',{'result':san,'errors':errors});assert not san.rejections and not san.unsafe_modes and not errors
  out=base/'sanitized-output';assert not (base/'host_metrics.json').exists();gate=checks.grade(unit,out);save(base/'verdict.json',gate)
  assert gate['admissible'] and gate['detail']['score_source']=='self_reported' and gate['detail']['rankable'] is False
  contract=checks.snapshot(unit,out,card);save(base/'output_contract.json',contract);assert all(x['status']=='PASS' for x in contract.values())
  n=_host_n_events(out,batch);assert n==_reported_n_events(out,batch)
  ev=json.loads((out/('batch_events.json' if batch else 'events.json')).read_text());sw=ev['wall_clock_sec'];assert abs(ev['events_per_sec']-n/sw)<max(1,n/sw)*1e-8
  assert abs(gate['score']-ev['events_per_sec'])<max(1,ev['events_per_sec'])*1e-8
  comparisons=[]
  for prior in ledger[:-1]:
   if prior['unit']!=name:continue
   priorbase=O/prior['path'];old=json.loads((priorbase/'output_contract.json').read_text());assert checks.identical(contract,old),'stable output mismatch'
   assert (priorbase/'stderr.log').read_bytes()==proc.stderr,'ordered stderr difference'
   comparisons.append(prior['index'])
  rec.update(state='PASS',score_source='self_reported',developer='PASS',supplemental='PASS',stable_comparisons=comparisons,n_events=n,self_wall_sec=sw,self_events_per_sec=n/sw,host_events_per_sec=n/wall,self_peak_rss_bytes=max(x['actual_events']['peak_memory_bytes'] for x in contract.values()),self_memory_source='process lifetime getrusage peak RSS; batch max child, not summed',output_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()))
 except BaseException as ex:
  rec.update(state='FAIL',error=type(ex).__name__+': '+str(ex));(base/'exception.txt').write_text(traceback.format_exc());raise
 finally:
  rec['end']=datetime.datetime.now(datetime.timezone.utc).isoformat();save(base/'run_record.json',rec);reconcile();print('DONE',idx,rec['state'],flush=True)
  if rec['state']=='PASS':subprocess.run(['docker','rm',cname],check=True,capture_output=True)
def review(unit):
 rows=[]
 for order in ['FI','IF']:
  runs={x['version']:x for x in ledger if x['unit']==unit and x['stage']=='formal' and x['order']==order};assert set(runs)=={'F','I'}
  r={'unit':unit,'order':order,'F_index':runs['F']['index'],'I_index':runs['I']['index'],'events':runs['F']['n_events']};assert r['events']==runs['I']['n_events']
  for metric in ['self','host']:
   f=runs['F'][metric+'_wall_sec'];i=runs['I'][metric+'_wall_sec'];r.update({metric+'_F_sec':f,metric+'_I_sec':i,metric+'_time_change_pct':(i/f-1)*100,metric+'_delta_sec':i-f,metric+'_EPS_ratio':f/i})
  rows.append(r);pairs.append(r)
 save(O/'pairs.json',pairs)
 for m in ['self','host']:
  assert not all(r[m+'_time_change_pct']>5 and r[m+'_delta_sec']>.05 for r in rows),'MATERIAL_REPEAT_REGRESSION '+unit+' '+m
def main():
 O.mkdir(exist_ok=True);assert not (O/'calls.json').exists(),'refuse repeat controller';save(O/'schedule.json',schedule());engine=preflight()
 for index,item in enumerate(schedule()):
  one(item,engine)
  if item['stage']=='formal' and item['order']=='IF' and item['version']=='F':review(item['unit'])
 assert len(ledger)==26 and len(pairs)==8
 ratios={m:statistics.geometric_mean(r[m+'_EPS_ratio'] for r in pairs) for m in ['self','host']}
 mixed=any(v<1 for v in ratios.values())
 save(O/'decision.json',{'state':'CFS_RUNTIME_PASS_PERFORMANCE_REVIEW' if mixed else 'RELEASE_REVIEW_READY_WITH_FULL_CPUSET_AND_CFS_SPOTCHECK','resource_and_outputs':'CFS_SPOTCHECK_PASS','calls':26,'pair_geomean_EPS_ratios':ratios,'rule':'geomean is descriptive; any negative overall metric conservatively held for performance review','full_CFS_validated':False,'I_promoted':False,'official_I_result':'unknown','writable_layer_1GiB':'unverified','official_hardware_launcher_equivalence':False,'independent_batch_children':0})
if __name__=='__main__':
 try:main()
 except BaseException as ex:
  O.mkdir(exist_ok=True);save(O/'decision.json',{'state':'STOPPED_ON_FAILURE','error':type(ex).__name__+': '+str(ex),'calls':len(ledger),'probes':probes,'full_CFS_validated':False,'I_promoted':False});(O/'exception.txt').write_text(traceback.format_exc());raise
