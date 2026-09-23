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
if __name__=='__main__':unittest.main()
