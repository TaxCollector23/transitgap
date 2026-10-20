"""Download a pinned prepared-data archive during build, never at request startup."""
import hashlib,io,os,tarfile,urllib.request
from pathlib import Path
url=os.environ.get('TRANSITGAP_DATA_ARCHIVE_URL','')
checksum=os.environ.get('TRANSITGAP_DATA_ARCHIVE_SHA256','')
if not url.startswith('https://') or len(checksum)!=64:raise SystemExit('Configure the real HTTPS prepared-data archive URL and SHA256 before deploying.')
root=Path('backend/data');root.mkdir(parents=True,exist_ok=True)
with urllib.request.urlopen(url,timeout=120) as source:
    archive=source.read(200*1024*1024+1)
if len(archive)>200*1024*1024 or hashlib.sha256(archive).hexdigest()!=checksum:raise SystemExit('Prepared-data archive exceeds the limit or failed checksum validation.')
with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as package:
    members=package.getmembers()
    if sum(m.size for m in members)>500*1024*1024:raise SystemExit('Prepared-data archive is too large.')
    for member in members:
        if not member.isfile() or '/' in member.name or member.name.startswith('.') or 'observation' in member.name.lower():raise SystemExit('Unexpected member in prepared-data archive.')
    package.extractall(root,members=members,filter='data')
print('Prepared public geographic data installed; community database is configured separately.')
