"""Bounded, explicitly partial output retention; all timing/metadata first."""
import hashlib,json,pathlib,tarfile
R=pathlib.Path(__file__).resolve().parent;O=R/'evidence';DEST=R/'artifact';CAP=100*1024**2;PAYLOAD_CAP=96*1024**2
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
if __name__=='__main__':
 DEST.mkdir(exist_ok=False);O.mkdir(exist_ok=True);files=[]
 for p in sorted(O.rglob('*')):
  if p.is_symlink():raise RuntimeError('unexpected evidence symlink')
  if p.is_file():files.append({'path':str(p.relative_to(O)),'bytes':p.stat().st_size,'sha256':sha(p)})
 meta=[r for r in files if not r['path'].endswith('.parquet')];parquet=[r for r in files if r['path'].endswith('.parquet')]
 calls=json.loads((O/'calls.json').read_text()) if (O/'calls.json').exists() else {'records':[]}
 failed=next((r['path'] for r in calls['records'] if r['state']!='PASS'),None)
 chosen=list(meta);used=sum(r['bytes'] for r in chosen);seen={};representatives={};omitted=[]
 for row in sorted(parquet,key=lambda x:(0 if failed and x['path'].startswith(failed+'/') else 1,x['path'])):
  digest=row['sha256'];isfailure=bool(failed and row['path'].startswith(failed+'/'));call=next((r for r in calls['records'] if row['path'].startswith(r['path']+'/')),None)
  if digest in seen:row['retention']={'kind':'byte-identical-alias','retained_path':seen[digest]};continue
  if call and call['unit'] not in representatives:representatives[call['unit']]=call['path']
  wanted=isfailure or (call and representatives[call['unit']]==call['path'])
  if wanted and used+row['bytes']<=PAYLOAD_CAP:
   chosen.append(row);used+=row['bytes'];seen[digest]=row['path'];row['retention']={'kind':'retained'}
  else:row['retention']={'kind':'NOT_BACKED_UP','reason':'success representative policy' if not wanted else 'artifact byte cap'};omitted.append(row['path'])
 inventory={'files':files,'all_metadata_retained':True,'selected_bytes':used,'cap_bytes':CAP,'omitted_parquet':omitted,'complete_parquet_backup':not omitted,'first_failure':failed,'policy':'metadata all; first failure Parquet priority; one success invocation per unit; duplicate byte aliases; no old evidence/images'}
 (O/'retention.json').write_text(json.dumps(inventory,indent=2)+'\n')
 if used+(O/'retention.json').stat().st_size>PAYLOAD_CAP:
  (DEST/'RETENTION_BLOCKED.json').write_text(json.dumps({'state':'ARTIFACT_OVER_BUDGET','metadata_bytes':sum(r['bytes'] for r in meta),'full_evidence_not_uploaded':True},indent=2)+'\n');raise SystemExit(1)
 out=DEST/'core004c-evidence.tar.gz'
 with tarfile.open(out,'w:gz') as t:
  for row in chosen:t.add(O/row['path'],arcname=row['path'],recursive=False)
  t.add(O/'retention.json',arcname='retention.json')
 assert out.stat().st_size+1024<CAP
 (DEST/'SHA256.json').write_text(json.dumps({'file':out.name,'bytes':out.stat().st_size,'sha256':sha(out),'scope':'selected new evidence only'},indent=2)+'\n')
