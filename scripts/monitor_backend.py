"""Lightweight health probe; a passing probe does not prove route correctness."""
import json,os,sys,urllib.request,urllib.error
base=os.getenv('TRANSITGAP_API_URL','').rstrip('/')
if not base:
    print('TRANSITGAP_API_URL is not configured. Set the repository Actions variable to the public backend HTTPS origin.');sys.exit(1)
if not base.startswith('https://'):
    print('TRANSITGAP_API_URL must be an HTTPS origin.');sys.exit(1)
try:
    with urllib.request.urlopen(base+'/health',timeout=45) as response:
        data=json.load(response)
        if response.status!=200 or not data.get('ready'):raise ValueError('Backend responded but is not ready')
        print('HTTP 200; health ready=true. This check did not calculate a route.')
except Exception as error:
    print('Backend health check failed:',type(error).__name__);sys.exit(1)
