"""Offline controls only: schedule, timestamps, statistics, failure and staging boundaries."""
import copy
import json
import pathlib
import tempfile
import unittest
import final_policy as policy
import resources

ROOT = pathlib.Path(__file__).resolve().parent
PLAN = json.loads((ROOT/'final_plan.json').read_text())


class FinalControls(unittest.TestCase):
    def rows(self, version='I', times=(99,1,2,3,4)):
        return [dict(unit='synthetic', version=version, repeat=k, index=k+1,
                     state='PASS', n_events=100, block_order='FI',
                     daemon_wall_sec=t, self_wall_sec=t, host_wall_sec=t)
                for k,t in enumerate(times)]

    def test_five_consecutive_block_counts_and_budget(self):
        initial, fallback = policy.schedule(PLAN), policy.schedule(PLAN, True)
        self.assertEqual(len(initial),60);self.assertEqual(len(fallback),20)
        self.assertEqual(sum(r['version']=='I' for r in initial),40)
        self.assertEqual(sum(r['version']=='F' for r in initial),20)
        for rows in (initial,fallback):
            for start in range(0,len(rows),5):
                block=rows[start:start+5]
                self.assertEqual([r['repeat'] for r in block],list(range(5)))
                self.assertEqual([r['stage'] for r in block],['warmup']+['formal']*4)
                self.assertEqual(len({(r['unit'],r['version']) for r in block}),1)
        self.assertEqual(len({r['unit'] for r in initial if r['version']=='I'}),8)

    def test_counterbalanced_version_block_order(self):
        orders=[r['block_order'] for r in policy.schedule(PLAN) if r['version']=='I' and r['repeat']==0 and len(r['block_order'])==2]
        self.assertEqual(orders,['FI','IF','FI','IF'])
        first={(r['unit'],r['version']) for r in policy.schedule(PLAN)}
        extra={(r['unit'],r['version']) for r in policy.schedule(PLAN,True)}
        self.assertFalse(first & extra)
        self.assertEqual({r['block_order'] for r in policy.schedule(PLAN,True)}, {'I_then_conditional_F'})

    def test_nanosecond_daemon_interval_and_offset(self):
        state={'Status':'exited','Running':False,'StartedAt':'2026-10-13T00:00:00.123456789Z','FinishedAt':'2026-10-13T08:00:01.123456790+08:00'}
        self.assertEqual(policy.daemon_seconds(state),1.000000001)

    def test_invalid_or_timeout_daemon_interval(self):
        state={'Status':'exited','Running':False,'StartedAt':'2026-10-13T00:00:00Z','FinishedAt':'2026-10-13T00:00:01Z'}
        for change in ({'Running':True},{'Status':'running'},{'StartedAt':'0001-01-01T00:00:00Z'},{'FinishedAt':'2026-10-13T00:05:00.000000001Z'},{'FinishedAt':'2026-10-13T00:00:00Z'},{'StartedAt':None},{'FinishedAt':'not-a-date'}):
            with self.subTest(change=change),self.assertRaises(ValueError):policy.daemon_seconds({**state,**change})

    def test_volume_forbidden_no_default_coercion(self):
        for value in ({},{'Volumes':None},{'Volumes':{}}):self.assertTrue(policy.no_volumes(value))
        for value in ({'Volumes':{'/data':{}}},{'Volumes':False},{'Volumes':[]},{'Volumes':''}):
            with self.assertRaises(AssertionError):policy.no_volumes(value)

    def test_median_of_four_rates_not_inverse_median_time(self):
        summary=policy.block_summary(self.rows())
        self.assertEqual(summary['daemon_median_sec'],2.5)
        self.assertAlmostEqual(summary['daemon_median_EPS'],(100/2+100/3)/2)
        self.assertNotEqual(summary['daemon_median_EPS'],100/2.5)
        self.assertEqual(summary['warmup_index'],1)

    def test_warmup_failure_never_discarded_as_success(self):
        for position in range(5):
            rows=self.rows();rows[position]['state']='FAIL'
            with self.assertRaises(AssertionError):policy.block_summary(rows)

    def test_missing_repeat_changed_count_and_bad_time_rejected(self):
        cases=[self.rows()[:4]]
        for field,value in [('n_events',101),('repeat',9),('daemon_wall_sec',float('nan')),('host_wall_sec',0),('self_wall_sec',True)]:
            rows=self.rows();rows[2][field]=value;cases.append(rows)
        for rows in cases:
            with self.assertRaises(AssertionError):policy.block_summary(rows)

    def test_regression_both_thresholds_and_separate_metrics(self):
        for f,i,flag in [(1,1.06,True),(1,1.04,False),(.1,.11,False)]:
            fs=policy.block_summary(self.rows('F',(f,)*5));is_=policy.block_summary(self.rows('I',(i,)*5))
            row=policy.comparisons([fs,is_])[0]
            self.assertEqual(row['material_daemon_regression'],flag)
        rows=self.rows('I',(1,)*5)
        for row in rows:row['self_wall_sec']=100
        result=policy.comparisons([policy.block_summary(self.rows('F',(1,)*5)),policy.block_summary(rows)])[0]
        self.assertFalse(result['material_daemon_regression'])
        self.assertGreater(result['self_time_change_pct'],5)

    def test_256mib_file_limit_other_resources_preserved(self):
        flags=resources.flags()
        self.assertIn('--ulimit=fsize=268435456:268435456',flags)
        for value in ('--cpus=4','--memory=16g','--memory-swap=16g','--runtime=runc','--network=none','--user=65534:65534','--pids-limit=256','--read-only','--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864,mode=1777'):
            self.assertIn(value,flags)
        self.assertFalse(any(x.startswith('--cpuset') or x.startswith('--workdir') for x in flags))

    def test_stable_binding_ignores_timing_but_not_trace(self):
        from final_checks import stable_equal
        left={'stable_binding':{'content_digest':'a','policy_digest':'p'},'timing':1}
        right={**left,'timing':2}
        self.assertTrue(stable_equal(left,right))
        right['stable_binding']={'content_digest':'b','policy_digest':'p'}
        self.assertFalse(stable_equal(left,right))

    def test_failure_classes_do_not_label_all_as_candidate(self):
        import final_run
        from qfbench2_common.contracts import OrganizerFault, ParticipantFailure
        self.assertEqual(final_run.failure_kind('RESOURCE_ENVIRONMENT',AssertionError()),'RESOURCE_ENVIRONMENT_FAILURE')
        self.assertEqual(final_run.failure_kind('CANDIDATE_RESOURCE',AssertionError()),'CANDIDATE_RESOURCE_OOM_UNDER_VERIFIED_LIMITS')
        self.assertEqual(final_run.failure_kind('OFFICIAL_CONTENT_CHECK',AssertionError()),'CANDIDATE_OUTPUT_FAILURE')
        self.assertEqual(final_run.failure_kind('OFFICIAL_CONTENT_CHECK',KeyError()),'CHECKER_OR_PACKAGING_FAILURE_REQUIRES_REVIEW')
        self.assertEqual(final_run.failure_kind('OFFICIAL_CONTENT_CHECK',OrganizerFault('bad reference')),'ORGANIZER_REFERENCE_OR_CONTRACT_FAILURE')
        self.assertEqual(final_run.failure_kind('OFFICIAL_CONTENT_CHECK',ParticipantFailure('bad sidecar')),'CANDIDATE_OUTPUT_FAILURE')

    def test_actual_runtime_readback_and_separate_oom_classification(self):
        actual={'Image':'fixed','Config':{'WorkingDir':'/tmp','User':'65534:65534'},'State':{'OOMKilled':False},
                'Mounts':[{'Destination':'/input','RW':False},{'Destination':'/output','RW':True}],
                'HostConfig':{'Runtime':'runc','NanoCpus':4000000000,'CpusetCpus':'','CpuShares':0,
                              'Memory':17179869184,'MemorySwap':17179869184,'PidsLimit':256,
                              'ReadonlyRootfs':True,'NetworkMode':'none','CapDrop':['ALL'],
                              'SecurityOpt':['no-new-privileges'],
                              'Tmpfs':{'/tmp':'rw,noexec,nosuid,nodev,size=67108864,mode=1777'},
                              'Ulimits':[{'Name':name,'Soft':n,'Hard':n} for name,n in [('nofile',1024),('nproc',256),('fsize',268435456)]]}}
        resources.check_inspect(actual,'fixed')
        bad=copy.deepcopy(actual);bad['HostConfig']['Runtime']='runsc'
        with self.assertRaises(AssertionError):resources.check_inspect(bad,'fixed')
        actual['State']['OOMKilled']=True
        with self.assertRaises(AssertionError):resources.check_inspect(actual,'fixed')
        # Final controller first verifies limits, then classifies the actual OOM explicitly.
        resources.check_inspect(actual,'fixed',check_exit=False)

    def test_official_staging_never_mounts_reference(self):
        from throughput.run_unit import _stage_input
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);unit=root/'unit';unit.mkdir();out=root/'input';out.mkdir()
            (unit/'scenario.json').write_text('{"seed":17}')
            (unit/'trace.parquet').write_bytes(b'REFERENCE_SECRET')
            (unit/'card.toml').write_text('reference_sha="not-runtime"')
            _stage_input(unit,out,False)
            self.assertEqual([p.name for p in out.iterdir()],['scenario.json'])
            self.assertEqual((out/'scenario.json').read_bytes(),(unit/'scenario.json').read_bytes())


if __name__=='__main__':unittest.main()
