from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, timezone
import uuid, json, math
from .database import connect
from .estimation import CATEGORY_META, MATERIALS, estimate, indices
bp=Blueprint('main',__name__)
now=lambda:datetime.now(timezone.utc).isoformat()
def rows(sql,args=()):
    with connect() as c:return [dict(x) for x in c.execute(sql,args).fetchall()]
def one(sql,args=()):
    with connect() as c:
        x=c.execute(sql,args).fetchone(); return dict(x) if x else None
@bp.get('/')
def home():return render_template('index.html')
@bp.get('/api/meta')
def meta():return jsonify(categories=CATEGORY_META,materials=MATERIALS)
@bp.route('/api/equipment',methods=['GET','POST'])
def equipment():
    if request.method=='GET':return jsonify(rows('SELECT * FROM historical_equipment ORDER BY created_at DESC'))
    d=request.json; d['id']=str(uuid.uuid4()); d['created_at']=now()
    cols=['id','category','subtype','size','size_unit','weight_kg','material','design_pressure_bar','design_temperature_c','power_kw','year','cost_original','currency','vendor_country','install_country','notes','created_at']
    with connect() as c:c.execute(f"INSERT INTO historical_equipment({','.join(cols)}) VALUES({','.join('?'*len(cols))})",[d.get(x) for x in cols])
    return jsonify(d),201
@bp.delete('/api/equipment/<id>')
def delete_equipment(id):
    with connect() as c:c.execute('DELETE FROM historical_equipment WHERE id=?',(id,))
    return jsonify(deleted=True)
@bp.route('/api/projects',methods=['GET','POST'])
def projects():
    if request.method=='GET':return jsonify(rows('SELECT * FROM projects ORDER BY created_at DESC'))
    d=request.json; d.update(id=str(uuid.uuid4()),created_at=now()); d.setdefault('description',''); d.setdefault('output_currency','EUR'); d.setdefault('target_year',datetime.now().year)
    with connect() as c:c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',(d['id'],d['name'],d['description'],d['output_currency'],d['target_year'],d['created_at']))
    return jsonify(d),201
@bp.get('/api/projects/<pid>')
def project(pid):
    p=one('SELECT * FROM projects WHERE id=?',(pid,)); rr=rows('SELECT * FROM equipment_rows WHERE project_id=? ORDER BY created_at',(pid,))
    if not p:return jsonify(error='Project not found'),404
    total=sum(x['total_expected_cost'] or 0 for x in rr); hr=[max(abs((x['unit_expected_cost']-x['unit_low'])*x['quantity']),abs((x['unit_high']-x['unit_expected_cost'])*x['quantity'])) for x in rr]
    h=math.sqrt(sum(x*x for x in hr)); cls=max([x['aace_class'] for x in rr],key=lambda x:int(x[-1]),default='Class 5')
    return jsonify(project=p,rows=rr,totals={'expected':total,'low':total-h,'high':total+h,'aace_class':cls})
@bp.delete('/api/projects/<pid>')
def delete_project(pid):
    with connect() as c:c.execute('DELETE FROM projects WHERE id=?',(pid,))
    return jsonify(deleted=True)
@bp.post('/api/projects/<pid>/rows')
def add_row(pid):
    d=request.json; p=one('SELECT * FROM projects WHERE id=?',(pid,))
    if not p:return jsonify(error='Project not found'),404
    e=estimate({**d,'target_year':p['target_year'],'output_currency':p['output_currency']}); q=max(1,int(d.get('quantity',1)))
    d.update(id=str(uuid.uuid4()),project_id=pid,created_at=now(),unit_expected_cost=e['expected'],unit_low=e['low'],unit_high=e['high'],total_expected_cost=round(e['expected']*q,2),total_sigma=round(e['sigma']*math.sqrt(q),2),aace_class=e['aace_class'],references_used=e['references_used'],escalation_factor=e['escalation_factor'],quantity=q)
    cols=['id','project_id','tag','category','subtype','size','size_unit','material','design_pressure_bar','design_temperature_c','power_kw','quantity','reference_ids','unit_expected_cost','unit_low','unit_high','total_expected_cost','total_sigma','aace_class','references_used','escalation_factor','created_at']
    d['reference_ids']=json.dumps(d.get('reference_ids') or [])
    with connect() as c:c.execute(f"INSERT INTO equipment_rows({','.join(cols)}) VALUES({','.join('?'*len(cols))})",[d.get(x) for x in cols])
    return jsonify(d),201
@bp.delete('/api/projects/<pid>/rows/<rid>')
def delete_row(pid,rid):
    with connect() as c:c.execute('DELETE FROM equipment_rows WHERE id=? AND project_id=?',(rid,pid))
    return jsonify(deleted=True)
@bp.route('/api/settings',methods=['GET','PUT'])
def settings():
    if request.method=='GET':return jsonify(rows('SELECT * FROM settings ORDER BY category'))
    with connect() as c:
        for x in request.json:c.execute('UPDATE settings SET scale_exponent=?,steel_weight=?,oil_weight=? WHERE category=?',(x['scale_exponent'],x['steel_weight'],x['oil_weight'],x['category']))
    return jsonify(ok=True)
@bp.get('/api/indices')
def api_indices():
    s,o=indices(); return jsonify(steel=s,oil=o,source='FRED if configured, otherwise local fallback')
