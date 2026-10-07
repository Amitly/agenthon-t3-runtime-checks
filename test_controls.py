"""No Docker/simulations: reject quota/identity and budget/order drift."""
import copy,json,pathlib,tempfile,unittest
import resources
class Controls(unittest.TestCase):
 def fixture(self):
  row={n:'unavailable' for n in ['cpu.max','cpu.cfs_quota_us','cpu.cfs_period_us','memory.max','memory.swap.max','memory.limit_in_bytes','memory.memsw.limit_in_bytes','pids.max']}
  row.update({'cpu.max':'400000 100000','memory.max':'17179869184','memory.swap.max':'0','pids.max':'256'})
  return {'ancestors':[row],'process_status':'Cpus_allowed_list:\t0-3'}
 def test_cfs_v2_actual(self):self.assertTrue(resources.check_cgroups(self.fixture()))
 def test_missing_or_fake_quota_rejected(self):
  for q in ['unavailable','max 100000','200000 100000']:
   x=self.fixture();x['ancestors'][0]['cpu.max']=q
   with self.assertRaises(AssertionError):resources.check_cgroups(x)
 def test_parent_quota_rejected(self):
  x=self.fixture();parent=copy.deepcopy(x['ancestors'][0]);parent['cpu.max']='200000 100000';x['ancestors'].append(parent)
  with self.assertRaises(AssertionError):resources.check_cgroups(x)
 def test_swap_and_memory_rejected(self):
  for k,v in [('memory.max','8589934592'),('memory.swap.max','max')]:
   x=self.fixture();x['ancestors'][0][k]=v
   with self.assertRaises(AssertionError):resources.check_cgroups(x)
 def test_v1_actual(self):
  x=self.fixture();r=x['ancestors'][0];r.update({'cpu.max':'unavailable','cpu.cfs_quota_us':'400000','cpu.cfs_period_us':'100000','memory.max':'unavailable','memory.limit_in_bytes':'17179869184','memory.memsw.limit_in_bytes':'17179869184'});self.assertTrue(resources.check_cgroups(x))
 def test_config_representation_and_rejections(self):
  expected={'WorkingDir':'/tmp','Env':['A=1','B=2']};self.assertEqual(len(resources.compare_config({**expected,'Tty':False,'Entrypoint':None},expected)),2)
  for changed in [{**expected,'Tty':0},{**expected,'Unexpected':None},{**expected,'WorkingDir':'/work'},{**expected,'Env':['B=2','A=1']},{**expected,'Entrypoint':[]}]:
   with self.assertRaises(AssertionError):resources.compare_config(changed,expected)
 def test_schedule(self):
  import run_ci
  rows=run_ci.schedule();self.assertEqual(len(rows),26);self.assertEqual(sum(r['stage']=='initial' for r in rows),2);self.assertEqual(sum(r['stage']=='warmup' for r in rows),8)
  for u in run_ci.C['units'][2:]:self.assertEqual(''.join(r['version'] for r in rows if r['unit']==u and r['stage']=='formal'),'FIIF')
 def test_stop_both_orders_same_metric(self):
  import run_ci
  with tempfile.TemporaryDirectory() as d:
   previous=(run_ci.O,run_ci.ledger,run_ci.pairs);run_ci.O=pathlib.Path(d)
   try:
    for ft,it,stopped in [(1,1.06,True),(1,1.04,False),(.1,.11,False)]:
     run_ci.pairs=[];run_ci.ledger=[{'version':v,'unit':'synthetic','stage':'formal','order':order,'index':i,'n_events':100,'self_wall_sec':ft if v=='F' else it,'host_wall_sec':ft if v=='F' else it} for i,(order,v) in enumerate((('FI','F'),('FI','I'),('IF','I'),('IF','F'))) ]
     if stopped:
      with self.assertRaises(AssertionError):run_ci.review('synthetic')
     else:run_ci.review('synthetic')
   finally:run_ci.O,run_ci.ledger,run_ci.pairs=previous


class FrozenImageRegression(unittest.TestCase):
 def setUp(self):
  self.root=pathlib.Path(__file__).resolve().parent
  self.frozen=json.loads((self.root/'frozen.json').read_text())
  self.fixtures=json.loads((self.root/'identity/inspect-regressions.json').read_text())
 def data(self,version):
  actual=copy.deepcopy(self.fixtures[version]['inspect']);expected=copy.deepcopy(self.frozen[version])
  manifest=(self.root/'identity'/(version+'.manifest.json')).read_bytes()
  raw=(self.root/'identity'/(version+'.config.json')).read_bytes()
  return actual,expected,manifest,raw
 def identity(self,version):
  a,f,m,r=self.data(version)
  return a,f,resources.verify_identity(m,r,f,a)
 def test_original_failure_and_fixed_real_F_I(self):
  # This is the original root comparator, not a new simulated failure payload.
  def legacy(actual,expected):
   defaults={'Hostname':'','Domainname':'','Image':'','User':'','AttachStdin':False,'AttachStdout':False,'AttachStderr':False,'Tty':False,'OpenStdin':False,'StdinOnce':False,'Entrypoint':None,'OnBuild':None,'Volumes':None}
   for k in set(actual)|set(expected):
    if k in actual and k in expected:
     assert type(actual[k]) is type(expected[k]) and actual[k]==expected[k],k
    else:
     present=actual[k] if k in actual else expected[k]
     assert k in defaults and type(present) is type(defaults[k]) and present==defaults[k],k
  a,f,_=self.identity('F')
  with self.assertRaisesRegex(AssertionError,'^Image$'):legacy(a['Config'],f['config'])
  for v in ('F','I'):
   with self.subTest(version=v):
    a,f,identity=self.identity(v)
    self.assertIsInstance(resources.compare_config(a['Config'],f['config'],identity),list)
 def test_all_three_bound_config_comparisons(self):
  for v in ('F','I'):
   a,f,identity=self.identity(v);raw=identity.raw['config']
   for name,left,right in [('actual_vs_frozen',a['Config'],f['config']),('actual_vs_raw',a['Config'],raw),('frozen_vs_raw',f['config'],raw)]:
    with self.subTest(version=v,comparison=name):
     self.assertEqual(resources.config_comparison_report(left,right,identity)['status'],'PASS')
   # Equal poisoned projections still cannot agree with the digest-bound raw config.
   altered=copy.deepcopy(a['Config']);altered['Env']=['POISON=1']
   self.assertEqual(resources.config_comparison_report(altered,altered,identity)['status'],'PASS')
   self.assertEqual(resources.config_comparison_report(altered,raw,identity)['status'],'FAIL')
 def test_bound_Image_representations(self):
  for v in ('F','I'):
   a,f,identity=self.identity(v);bound=json.loads(self.data(v)[3])['config']['Image']
   for left in ('absent','default','raw'):
    for right in ('absent','default','raw'):
     with self.subTest(version=v,actual=left,expected=right):
      x=copy.deepcopy(a['Config']);y=copy.deepcopy(f['config'])
      for z,kind in ((x,left),(y,right)):
       z.pop('Image',None)
       if kind!='absent':z['Image']='' if kind=='default' else bound
      resources.compare_config(x,y,identity)
 def test_unbound_nonempty_Image_rejected_even_if_equal(self):
  for value in ['sha256:'+'1'*64,'arbitrary']:
   for a,e in [({'Image':value},{}),({}, {'Image':value}),({'Image':value},{'Image':value})]:
    with self.subTest(actual=a,expected=e):
     with self.assertRaises(AssertionError):resources.compare_config(a,e)
 def test_wrong_Image_value_type_or_other_image_rejected(self):
  for v in ('F','I'):
   a,f,identity=self.identity(v);other=json.loads(self.data('I' if v=='F' else 'F')[3])['config']['Image']
   for bad in [None,False,0,[],{},'garbage','sha256:'+'a'*64,other]:
    for side in ('actual','expected','both'):
     with self.subTest(version=v,value=bad,side=side):
      x=copy.deepcopy(a['Config']);y=copy.deepcopy(f['config'])
      if side in ('actual','both'):x['Image']=bad
      if side in ('expected','both'):y['Image']=bad
      with self.assertRaises(AssertionError):resources.compare_config(x,y,identity)
 def test_runtime_fields_and_unknown_fields_stay_strict(self):
  mutations={'Cmd':['echo','wrong'],'Entrypoint':['wrong'],'Env':['BAD=1'],'WorkingDir':'/work','User':'root','Labels':{'qfbench2.interface_version':'wrong'},'Unknown':None,'Tty':0}
  for v in ('F','I'):
   a,f,identity=self.identity(v)
   for k,bad in mutations.items():
    with self.subTest(version=v,field=k):
     x=copy.deepcopy(a['Config']);x[k]=bad
     with self.assertRaises(AssertionError):resources.compare_config(x,f['config'],identity)
   x=copy.deepcopy(a['Config']);x['Env']=list(reversed(x['Env']))
   with self.assertRaises(AssertionError):resources.compare_config(x,f['config'],identity)
 def test_nested_types_are_not_coerced(self):
  for a,e in [({'Labels':{'x':False}},{'Labels':{'x':0}}),({'Cmd':[False]},{'Cmd':[0]})]:
   with self.assertRaises(AssertionError):resources.compare_config(a,e)
 def test_identity_tamper_rejected_before_representation(self):
  for v in ('F','I'):
   a,f,m,r=self.data(v)
   for name,bad in [('Id','sha256:'+'0'*64),('Architecture','arm64'),('Os','windows'),('RootFS',{'Type':'layers','Layers':list(reversed(a['RootFS']['Layers']))})]:
    with self.subTest(version=v,field=name):
     x=copy.deepcopy(a);x[name]=bad
     with self.assertRaises(AssertionError):resources.verify_identity(m,r,f,x)
   for name,mm,rr in [('manifest',m+b' ',r),('config',m,r+b' '),('other_config',m,self.data('I' if v=='F' else 'F')[3])]:
    with self.subTest(version=v,tamper=name):
     with self.assertRaises(AssertionError):resources.verify_identity(mm,rr,f,a)
 def test_all_config_differences_are_reported(self):
  a,f,identity=self.identity('F');a['Config'].update(Image='wrong',WorkingDir='/work',Unknown=True)
  with self.assertRaises(AssertionError) as caught:resources.compare_config(a['Config'],f['config'],identity)
  report=caught.exception.report
  rendered=json.dumps(report)
  self.assertTrue(all(k in rendered for k in ('Image','WorkingDir','Unknown')))

if __name__=='__main__':unittest.main()
