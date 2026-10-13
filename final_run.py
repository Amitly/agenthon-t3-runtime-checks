"""Explicit replacement: bounded Final-style local acceptance; never an official Final scorer."""
import csv,dataclasses,datetime,enum,hashlib,importlib.metadata,json,os,pathlib,platform,shutil,statistics,subprocess,sys,time,tomllib,traceback
P=pathlib.Path;ROOT=P(__file__).resolve().parent;O=ROOT/'evidence';N=ROOT/'track-src';C=json.loads((ROOT/'frozen.json').read_text())
sys.path.insert(0,str(N))
import checks,resources,final_policy,final_checks
PLAN=json.loads((ROOT/'final_plan.json').read_text());C={**C,**PLAN}
from throughput.run_unit import _stage_input,_host_n_events,_reported_n_events
from throughput.timer import timed_container_run
from qfbench2_common.sanitize import materialize_tree,verify_destination
from qfbench2_common.contracts.artifact_tree import TreeLimits
from qfbench2_common.contracts import OrganizerFault, ParticipantFailure
from qfbench2_track_simulation.limits import allowed_paths_for
from qfbench2_track_simulation import SCORER_VERSION
ledger=[];pairs=[];probes=[];summaries=[];controller_start=None;phase='PREFLIGHT';active_run=None
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
def reconcile():save(O/'calls.json',{'budget':80,'initial_plan':60,'conditional_F':20,'attempts':len(ledger),'passed':sum(x['state']=='PASS' for x in ledger),'probes':probes,'records':ledger,'builds':0,'uploads':0,'profiler_calls':0,'historical_26_plan':'REPLACED_NOT_ADDED'})
def schedule(fallback=False):return final_policy.schedule(PLAN,fallback)
def dirs(base):
 base.mkdir(parents=True,exist_ok=False);i=base/'input';o=base/'output';i.mkdir();o.mkdir();os.chown(o,65534,65534);o.chmod(0o755);return i,o
def node():
 info=json.loads(subprocess.check_output(['docker','info','--format={{json .}}']))
 return {'engine_id':info['ID'],'name':info['Name'],'os':info['OSType'],'architecture':info['Architecture'],'cgroup_version':info['CgroupVersion'],'endpoint':os.environ['DOCKER_HOST']}
def preflight():
 global phase
 phase='RESOURCE_ENVIRONMENT'
 assert os.environ.get('GITHUB_REPOSITORY')=='Amitly/agenthon-t3-runtime-checks'
 assert os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1'
 assert platform.machine()=='x86_64' and sys.version_info[:3]==(3,13,15)
 assert importlib.metadata.version('qfbench2-common')==C['common_version'] and SCORER_VERSION==C['scorer_version']
 os.environ.pop('DOCKER_CONTEXT',None);os.environ['DOCKER_HOST']='unix:///var/run/docker.sock'
 empty=ROOT/'empty-docker-config';empty.mkdir(mode=0o700,exist_ok=False);os.environ['DOCKER_CONFIG']=str(empty)
 assert not list(empty.iterdir())
 version=run(['docker','version']);save(O/'docker-version.json',{'argv':['docker','version'],'returncode':version.returncode,'stdout':version.stdout,'stderr':version.stderr});assert version.returncode==0
 engine=node();assert engine['os']=='linux' and engine['architecture'] in ['x86_64','amd64']
 assert not subprocess.check_output(['docker','ps','-q'],text=True).strip()
 save(O/'node.json',{'docker':engine,'uname':platform.uname()._asdict(),'cpu_topology':run(['lscpu','-e']).stdout,'online':resources.read('/sys/devices/system/cpu/online'),'allowed_cpus':sorted(os.sched_getaffinity(0)),'memory':resources.memory_guard(C['maximum_historical_peak_bytes']),'python':sys.version,'dependencies':{x.metadata['Name']:x.version for x in importlib.metadata.distributions()},'timing':'Primary actual Docker StartedAt/FinishedAt; whole CLI and self separate; no official C2 attestation or hardware equivalence'})
 phase='IMAGE_IDENTITY_CHECK'
 identities={};images={}
 for v in ['F','I']:
  manifest_bytes=(ROOT/'identity'/f'{v}.manifest.json').read_bytes();config_bytes=(ROOT/'identity'/f'{v}.config.json').read_bytes()
  (O/'identity').mkdir(exist_ok=True);(O/'identity'/f'{v}.manifest.json').write_bytes(manifest_bytes);(O/'identity'/f'{v}.config.json').write_bytes(config_bytes)
  before=subprocess.check_output(['docker','image','ls','--no-trunc'],text=True);p=run(['docker','pull','--platform=linux/amd64',C[v]['ref']],600)
  save(O/f'pull-{v}.json',{'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'before_images':before,'credentials':'fresh empty CLI config','ref':C[v]['ref']});assert p.returncode==0
  actual=inspect(C[v]['ref']);save(O/f'image-{v}.json',actual)
  try:identity=resources.verify_identity(manifest_bytes,config_bytes,C[v],actual)
  except resources.IdentityValidationError as ex:save(O/f'identity-{v}.json',ex.report);raise
  save(O/f'identity-{v}.json',identity.report);identities[v]=identity;images[v]=actual
 # Both immutable identities must pass before any representation exception applies.
 config_failures=[]
 for v in ['F','I']:
  identity=identities[v];actual=images[v];raw=identity.raw['config'];expected=C[v]['config']
  comparisons={name:resources.config_comparison_report(left,right,identity) for name,left,right in [
   ('actual_vs_frozen',actual['Config'],expected),('actual_vs_raw',actual['Config'],raw),('frozen_vs_raw',expected,raw)]}
  failures=[name+':'+field for name,report in comparisons.items() for field in report['failures']]
  report={'status':'FAIL' if failures else 'PASS','failures':failures,'image':v,'identity':identity.report,'comparisons':comparisons}
  save(O/f'config-representation-{v}.json',report)
  config_failures.extend(v+':'+failure for failure in failures)
 # Persist both already-collected images' complete comparisons before stopping.
 if config_failures:raise resources.ConfigComparisonError({'status':'FAIL','failures':config_failures,'reports':['config-representation-F.json','config-representation-I.json']})
 for v in ['F','I']:
  assert images[v]['Config']['WorkingDir']=='/tmp'
  final_policy.no_volumes(images[v]['Config']);final_policy.no_volumes(identities[v].raw['config'])
 phase='RESOURCE_ENVIRONMENT'
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
 global phase,active_run
 assert len(ledger)<80 and all(x['state']=='PASS' for x in ledger)
 if time.monotonic()-controller_start>PLAN['workflow_controller_limit_seconds']-330:raise RuntimeError('CONTROLLER_TIME_BUDGET_STOP_NO_RETRY')
 phase='RESOURCE_ENVIRONMENT';assert node()==engine
 memory=resources.memory_guard(C['maximum_historical_peak_bytes']);idx=len(ledger)+1;v=item['version'];name=item['unit'];unit=N/'units'/name;card=tomllib.loads((unit/'card.toml').read_text());batch=(unit/'batch.json').exists()
 phase='STAGING_WRAPPER'
 base=O/'simulations'/f'{idx:02d}-{item["stage"]}-{name}-{v}';i,o=dirs(base);_stage_input(unit,i,batch)
 # Official current public _stage_input remains scenario-only. No references, checks or card secrets are mounted.
 for path in i.rglob('*'):path.chmod(0o755 if path.is_dir() else 0o644)
 allowed={str(p.relative_to(unit/'scenarios')) for p in (unit/'scenarios').rglob('*') if p.is_file()} if batch else {'scenario.json'}
 actual_inputs={str(p.relative_to(i/'scenarios' if batch else i)) for p in i.rglob('*') if p.is_file()}
 assert actual_inputs==allowed and all(not p.is_symlink() for p in i.rglob('*'))
 input_files={str(p.relative_to(i)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in i.rglob('*') if p.is_file()}
 save(base/'input-inventory.json',{'files':input_files,'stage':'current pinned official _stage_input','reference_material_mounted':False,'card_mounted':False})
 verbs=['simulate-batch','--batch-dir','/input/scenarios','--out-dir','/output'] if batch else ['simulate','--config','/input/scenario.json','--out','/output/trace.parquet']
 cid=base/'container.cid';cname='t3-final-style-'+str(idx);args=['docker','run','--name',cname,'--cidfile',str(cid),*resources.flags(),'-v',str(i)+':/input:ro','-v',str(o)+':/output',C[v]['ref'],*verbs]
 rec={**item,'index':idx,'state':'STARTED','path':str(base.relative_to(O)),'image_id':C[v]['id'],'image':C[v]['ref'],'cpu_mode':'CFS_4','instrumented':False,'rankable':False,'family':card['task']['scenario_family'],'start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'memory_before':memory,'timeout_sec':300}
 ledger.append(rec);active_run=rec;reconcile();save(base/'launch.json',args);print('START',idx,v,name,flush=True)
 try:
  phase='CONTAINER_EXECUTION'
  with resources.Observe(cid) as obs:proc,wall,gpu,mem=timed_container_run(args,cidfile=cid,gpus=None,timeout_sec=300)
  (base/'stdout.log').write_bytes(proc.stdout);(base/'stderr.log').write_bytes(proc.stderr)
  rec.update(returncode=proc.returncode,host_wall_sec=wall,host_peak_memory_bytes=mem,host_memory_source='fixed timer cgroup sampler; not process RSS')
  save(base/'cgroups.json',{'first':obs.first,'last':obs.last,'error':obs.error})
  actual=inspect(cname);save(base/'inspect.json',actual)
  rec.update(daemon_started_at=actual['State']['StartedAt'],daemon_finished_at=actual['State']['FinishedAt'],daemon_timing_source='actual Docker inspect State timestamps',daemon_exit_code=actual['State']['ExitCode'],daemon_oom_killed=actual['State']['OOMKilled'],daemon_error=actual['State'].get('Error'),cli_deadline_exceeded_or_killed=proc.returncode<0,timeout_clock='local whole Docker CLI 300s cap; separately require daemon<=300s; not official timeout equivalence')
  phase='RESOURCE_ENVIRONMENT'
  assert obs.first and not obs.error;resources.check_cgroups(obs.first);resources.check_inspect(actual,C[v]['id'],check_exit=False)
  phase='CANDIDATE_RESOURCE'
  if actual['State']['OOMKilled']:raise AssertionError('Container OOMKilled under verified limits')
  phase='CONTAINER_EXECUTION'
  if proc.returncode!=0:raise AssertionError('Container exit code '+str(proc.returncode))
  rec['daemon_wall_sec']=final_policy.daemon_seconds(actual['State'])
  phase='OUTPUT_SANITIZATION'
  san=materialize_tree(o,base/'sanitized-output',limits=TreeLimits(max_depth=2,max_file_bytes=268435456,max_total_bytes=268435456),allowed_paths=allowed_paths_for(unit));errors=verify_destination(base/'sanitized-output',san.files);save(base/'sanitizer.json',{'result':san,'errors':errors});assert not san.rejections and not san.unsafe_modes and not errors
  phase='OFFICIAL_CONTENT_CHECK'
  out=base/'sanitized-output';assert not (base/'host_metrics.json').exists();gate=checks.grade(unit,out);save(base/'verdict.json',gate)
  assert gate['admissible'] and gate['detail']['score_source']=='self_reported' and gate['detail']['rankable'] is False
  contract=final_checks.current_contract(unit,out,card);save(base/'output_contract.json',contract)
  n=_host_n_events(out,batch);assert n==_reported_n_events(out,batch)==contract['n_events']
  ev=json.loads((out/('batch_events.json' if batch else 'events.json')).read_text());sw=ev['wall_clock_sec'];assert abs(ev['events_per_sec']-n/sw)<max(1,n/sw)*1e-8
  phase='STABLE_REPEAT_CHECK'
  same_version=[];cross_version=[]
  for prior in ledger[:-1]:
   if prior['unit']!=name:continue
   priorbase=O/prior['path'];old=json.loads((priorbase/'output_contract.json').read_text());same=final_checks.stable_equal(contract,old)
   if prior['version']==v:
    assert same,'Candidate own stable output mismatch';same_version.append(prior['index'])
   else:cross_version.append({'index':prior['index'],'equal':same})
  rec.update(state='PASS',score_source='self_reported_content_only',developer='PASS',supplemental='PASS',stable_comparisons=same_version,cross_candidate_stable_comparisons=cross_version,n_events=n,self_wall_sec=sw,self_events_per_sec=n/sw,host_events_per_sec=n/wall,daemon_events_per_sec=n/rec['daemon_wall_sec'],self_peak_rss_bytes=max(x['actual_events']['peak_memory_bytes'] for x in contract['sub_contracts'].values()),self_memory_source='process lifetime getrusage peak RSS; batch max child, not summed',output_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()))
 except BaseException as ex:
  classification=failure_kind(phase,ex)
  rec.update(state='FAIL',failure_phase=phase,failure_class=classification,error=type(ex).__name__+': '+str(ex));(base/'exception.txt').write_text(traceback.format_exc());raise
 finally:
  rec['end']=datetime.datetime.now(datetime.timezone.utc).isoformat();save(base/'run_record.json',rec);reconcile();print('DONE',idx,rec['state'],flush=True)
  if rec['state']=='PASS':subprocess.run(['docker','rm',cname],check=True,capture_output=True)

def failure_kind(at_phase,error):
 if isinstance(error,OrganizerFault):return 'ORGANIZER_REFERENCE_OR_CONTRACT_FAILURE'
 if isinstance(error,ParticipantFailure):return 'CANDIDATE_OUTPUT_FAILURE'
 if at_phase=='IMAGE_IDENTITY_CHECK':return 'IMAGE_IDENTITY_OR_CONFIG_PREFLIGHT_FAILURE'
 if at_phase=='RESOURCE_ENVIRONMENT':return 'RESOURCE_ENVIRONMENT_FAILURE'
 if at_phase=='CANDIDATE_RESOURCE':return 'CANDIDATE_RESOURCE_OOM_UNDER_VERIFIED_LIMITS'
 if at_phase=='CONTAINER_EXECUTION':return 'CONTAINER_OR_CLI_DEADLINE_FAILURE_REQUIRES_REVIEW'
 if at_phase in ('OUTPUT_SANITIZATION','OFFICIAL_CONTENT_CHECK','STABLE_REPEAT_CHECK') and isinstance(error,AssertionError):return 'CANDIDATE_OUTPUT_FAILURE'
 return 'CHECKER_OR_PACKAGING_FAILURE_REQUIRES_REVIEW'

def finish_block(item):
 block=[r for r in ledger if r['scope']==item['scope'] and r['block']==item['block']]
 summaries.append(final_policy.block_summary(block));save(O/'blocks.json',summaries)
 rows=final_policy.comparisons(summaries);save(O/'pairs.json',rows)
 return rows

def main():
 global controller_start,phase
 controller_start=time.monotonic();O.mkdir(exist_ok=True);assert not (O/'calls.json').exists(),'refuse repeat controller'
 save(O/'final_plan.json',PLAN);save(O/'schedule.json',{'initial':schedule(),'conditional_F':schedule(True)});reconcile();engine=preflight()
 rows=[]
 for item in schedule():
  one(item,engine)
  if item['repeat']==4:rows=finish_block(item)
 assert len(ledger)==60 and len(rows)==4
 regressions=[r for r in rows if r['material_daemon_regression']]
 save(O/'review-after-60.json',{'calls':60,'comparisons':rows,'material_daemon_regressions':regressions,'rule':PLAN['decision_rule'],'classification':'LOCAL_PERFORMANCE_RISK' if regressions else 'NO_MATERIAL_DAEMON_REGRESSION','candidate_output_status':'PASS'})
 selected='I'
 if regressions:
  selected='F'
  for item in schedule(True):
   one(item,engine)
   if item['repeat']==4:finish_block(item)
 assert len(ledger)==(80 if selected=='F' else 60)
 chosen=[s for s in summaries if s['version']==selected];assert len(chosen)==8
 save(O/'decision.json',{'state':'FINAL_STYLE_ACCEPTANCE_REVIEW_READY_'+selected,'selected_candidate_for_review':selected,'selected_image_ref':C[selected]['ref'],'selected_config_id':C[selected]['id'],'calls':len(ledger),'passed':len(ledger),'probes':probes,'checks':{'content':'PASS','resource':'PASS','ABI':'PASS_I_NATIVE_IMPORT_AND_ALL_CALLS','repeat':'PASS_5_PER_CANDIDATE_UNIT','timeout':'PASS_ALL_WARMUPS_AND_MEASURED_WITHIN_300S','volume':'PASS_NO_INHERITED_OR_EXPLICIT_VOLUME'},'current_contract':{'status':'PASS_LOCAL_CONTENT','track_commit':C['track_commit'],'common_commit':C['common_commit'],'common_version':C['common_version']},'material_I_daemon_regressions':regressions,'all_blocks':summaries,'timing':'actual daemon start-exit primary; self and complete CLI separate','official_rankable':False,'official_new_Development_score':'UNKNOWN','official_Final_result':'UNKNOWN','full_71_CFS_validated':False,'hidden_units_validated':False,'independent_batch_child_calls':0,'writable_layer_1GiB':'readonly root, no Docker storage-opt hard quota claimed','official_hardware_launcher_equivalence':False,'recommendation_accepted':False,'review_required':'independent inspection of raw calls, resources, output checks, repeat bindings and risk before private packaging','automatic_upload':False,'automatic_dispatch':False})
if __name__=='__main__':
 try:main()
 except BaseException as ex:
  O.mkdir(exist_ok=True);reconcile();save(O/'decision.json',{'state':'STOPPED_ON_FAILURE','failure_class':failure_kind(phase,ex),'failure_phase':phase,'error':type(ex).__name__+': '+str(ex),'calls':len(ledger),'probes':probes,'active_run':active_run,'full_71_CFS_validated':False,'recommendation_accepted':False,'automatic_upload':False,'automatic_dispatch':False});(O/'exception.txt').write_text(traceback.format_exc());raise
