"""Fetch only public pinned dependencies and selected LFS data, before timing."""
import hashlib,json,os,pathlib,subprocess,sys
P=pathlib.Path;ROOT=P(__file__).resolve().parent;C=json.loads((ROOT/'frozen.json').read_text())
def run(a,**kw):subprocess.run(a,check=True,**kw)
def checkout(name,url,commit):
 p=ROOT/name;p.mkdir(exist_ok=False)
 run(['git','init',str(p)]);run(['git','-C',str(p),'remote','add','origin',url])
 env={**os.environ,'GIT_LFS_SKIP_SMUDGE':'1','GIT_TERMINAL_PROMPT':'0'}
 run(['git','-C',str(p),'fetch','--depth=1','origin',commit],env=env)
 run(['git','-C',str(p),'checkout','--detach','FETCH_HEAD'],env=env)
 assert subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()==commit
 return p
if __name__=='__main__':
 assert sys.version_info[:3]==(3,13,15)
 common=checkout('common-src','https://github.com/Agenthon-2026/Agenthon2026-public.git',C['common_commit'])
 track=checkout('track-src','https://github.com/Agenthon-2026/track3-simulation-public.git',C['track_commit'])
 run(['git','-C',str(track),'lfs','pull','--include='+','.join('units/'+n+'/**' for n in C['units']),'--exclude='])
 refs=[]
 for n in C['units']:
  files=list((track/'units'/n).rglob('*.parquet'));assert files,n
  for p in files:
   with p.open('rb') as f:assert f.read(4)==b'PAR1',str(p)
   with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
   refs.append({'path':str(p.relative_to(track)),'bytes':p.stat().st_size,'sha256':h})
 (ROOT/'evidence').mkdir(exist_ok=True);(ROOT/'evidence/reference-inventory.json').write_text(json.dumps(refs,indent=2)+'\n')
 run([sys.executable,'-m','pip','install','--disable-pip-version-check','-r',str(ROOT/'requirements.txt')])
 # Common is always installed from the fixed official source, never a squattable bare PyPI name.
 run([sys.executable,'-m','pip','install','--no-deps',str(common/'common')+'[data]',str(track)])
 run([sys.executable,'-m','pip','check'])
