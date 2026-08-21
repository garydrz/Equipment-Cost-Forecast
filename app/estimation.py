import os, math, requests
from datetime import datetime, timezone
from .database import connect
CATEGORY_META={
"column":{"label":"Distillation Column","unit":"m3","power_field":False,"default_n":0.65,"steel_w":0.80,"oil_w":0.20},
"reactor":{"label":"Reactor","unit":"m3","power_field":False,"default_n":0.65,"steel_w":0.80,"oil_w":0.20},
"heat_exchanger":{"label":"Heat Exchanger","unit":"m2","power_field":False,"default_n":0.65,"steel_w":0.80,"oil_w":0.20},
"storage_tank":{"label":"Storage Tank","unit":"m3","power_field":False,"default_n":0.62,"steel_w":0.80,"oil_w":0.20},
"pump":{"label":"Pump","unit":"m3/h","power_field":True,"default_n":0.60,"steel_w":0.40,"oil_w":0.60},
"compressor":{"label":"Compressor","unit":"m3/h","power_field":True,"default_n":0.75,"steel_w":0.40,"oil_w":0.60},
"valve":{"label":"Valve","unit":"DN(mm)","power_field":False,"default_n":0.40,"steel_w":0.60,"oil_w":0.40},
"instrumentation":{"label":"Instrumentation","unit":"unit","power_field":False,"default_n":0.30,"steel_w":0.60,"oil_w":0.40},
"other":{"label":"Other","unit":"unit","power_field":False,"default_n":0.60,"steel_w":0.70,"oil_w":0.30}}
MATERIALS=["carbon_steel","stainless_steel_304","stainless_steel_316","duplex","alloy","other"]
AACE={"Class 5":(-.35,.65),"Class 4":(-.22,.35),"Class 3":(-.15,.20)}
STEEL={2005:88,2006:96,2007:106,2008:128,2009:90,2010:108,2011:128,2012:118,2013:112,2014:111,2015:100,2016:96,2017:108,2018:128,2019:118,2020:114,2021:190,2022:220,2023:178,2024:172,2025:176,2026:180}
OIL={2005:54,2006:65,2007:72,2008:97,2009:62,2010:80,2011:111,2012:112,2013:109,2014:99,2015:52,2016:44,2017:54,2018:71,2019:64,2020:42,2021:71,2022:100,2023:82,2024:80,2025:78,2026:78}

def fred_series(series):
    key=os.getenv('FRED_API_KEY','')
    if not key:return {}
    try:
        r=requests.get(os.getenv('FRED_API_BASE','https://api.stlouisfed.org/fred')+'/series/observations',params={'series_id':series,'api_key':key,'file_type':'json','frequency':'a','aggregation_method':'avg','observation_start':'2000-01-01'},timeout=12)
        r.raise_for_status(); return {int(x['date'][:4]):float(x['value']) for x in r.json().get('observations',[]) if x['value']!='.'}
    except Exception:return {}

def indices():
    return fred_series('WPU101706') or STEEL,fred_series('DCOILBRENTEU') or OIL

def val(s,y):
    ys=sorted(s); y=max(ys[0],min(ys[-1],y))
    if y in s:return s[y]
    lo=max(x for x in ys if x<y); hi=min(x for x in ys if x>y)
    return s[lo]+(y-lo)/(hi-lo)*(s[hi]-s[lo])

def fx(base,target,year=None):
    if base==target:return 1.0
    date=f'{year}-06-15' if year else 'latest'
    try:
        u=os.getenv('FX_API_BASE','https://api.frankfurter.dev/v1')+f'/{date}'
        r=requests.get(u,params={'base':base,'symbols':target},timeout=10); r.raise_for_status()
        return float(r.json()['rates'][target])
    except Exception:return 1.08 if base=='EUR' else 0.9259259

def classify(n): return 'Class 3' if n>=5 else ('Class 4' if n>=3 else 'Class 5')
def estimate(data):
    cat=data['category']; target=int(data['target_year']); out=data.get('output_currency','EUR')
    with connect() as con:
        cfg=dict(con.execute('SELECT * FROM settings WHERE category=?',(cat,)).fetchone())
        refs=[dict(x) for x in con.execute('SELECT * FROM historical_equipment WHERE category=?',(cat,)).fetchall()]
    n=cfg['scale_exponent']; sw=cfg['steel_weight']; ow=cfg['oil_weight']; steel,oil=indices(); costs=[]; escs=[]
    use_power=CATEGORY_META[cat]['power_field'] and data.get('power_kw')
    target_size=float(data.get('power_kw') if use_power else data['size'])
    for r in refs:
        ref_size=float(r['power_kw'] if use_power and r.get('power_kw') else r['size'])
        if ref_size<=0 or target_size<=0:continue
        esc=1+sw*(val(steel,target)-val(steel,int(r['year'])))/val(steel,int(r['year']))+ow*(val(oil,target)-val(oil,int(r['year'])))/val(oil,int(r['year']))
        costs.append(float(r['cost_original'])*(target_size/ref_size)**n*esc*fx(r['currency'],out,target)); escs.append(esc)
    nr=len(costs); cls=classify(nr)
    if not nr:return {'expected':0,'low':0,'high':0,'sigma':0,'references_used':0,'aace_class':cls,'escalation_factor':0}
    mean=sum(costs)/nr; lp,hp=AACE[cls]
    if nr>=3:
        sigma=math.sqrt(sum((x-mean)**2 for x in costs)/(nr-1)); low=min(mean*(1+lp),mean-sigma); high=max(mean*(1+hp),mean+sigma)
    else:
        low=mean*(1+lp); high=mean*(1+hp); sigma=(high-low)/3.29
    return {k:round(v,2) if isinstance(v,float) else v for k,v in {'expected':mean,'low':low,'high':high,'sigma':sigma,'references_used':nr,'aace_class':cls,'escalation_factor':sum(escs)/len(escs)}.items()}
