"""Join OSM boundary ways, classify source coordinates, simplify display only.
Input boundary data and derived geometry are ODbL-1.0; see docs/ops/MOSCOW_DISTRICT_MAP.md.
"""
import json,math,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
if len(sys.argv)!=3: raise SystemExit('Usage: build_moscow_district_map.py OSM_JSON COORDINATES_JSON')
data=json.load(open(sys.argv[1]))
def join(parts):
 parts=[[(round(p['lon'],7),round(p['lat'],7)) for p in x] for x in parts]
 rings=[]
 while parts:
  chain=parts.pop()
  while chain[0]!=chain[-1]:
   found=False
   for i,p in enumerate(parts):
    if p[0]==chain[-1]:chain+=p[1:];parts.pop(i);found=True;break
    if p[-1]==chain[-1]:chain+=list(reversed(p))[1:];parts.pop(i);found=True;break
   if not found:raise ValueError('Unclosed boundary')
  rings.append(chain)
 return rings
def inside(pt,ring):
 x,y=pt;result=False
 for (ax,ay),(bx,by) in zip(ring,ring[1:]):
  if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax:result=not result
 return result
def rdp(points,epsilon):
 if len(points)<3:return points
 a,b=points[0],points[-1];dx=b[0]-a[0];dy=b[1]-a[1];length=dx*dx+dy*dy
 def dist(p):
  t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0
  return ((p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2)**.5
 ds=[dist(p) for p in points[1:-1]];m=max(ds);i=ds.index(m)+1
 return rdp(points[:i+1],epsilon)[:-1]+rdp(points[i:],epsilon) if m>epsilon else [a,b]
allrows=[]
for el in data['elements']:
 tags=el['tags'];name=tags.get('name:ru',tags['name']);name=re.sub(r'^район | район$','',name)
 members=el['members'];outer=join([m['geometry'] for m in members if m['type']=='way' and m['role']=='outer']);inner=join([m['geometry'] for m in members if m['type']=='way' and m['role']=='inner'])
 assert outer
 allrows.append({'id':str(el['id']),'name':name,'outer':outer,'inner':inner})
coords=json.load(open(sys.argv[2]));enriched=[]
for point in coords:
 if 'lat' not in point:enriched.append(point);continue
 match=[r for r in allrows if any(inside((point['lon'],point['lat']),o) for o in r['outer']) and not any(inside((point['lon'],point['lat']),h) for h in r['inner'])]
 assert len(match)<=1,(point,[(r['id'],r['name']) for r in match])
 enriched.append({**point,'district_id':match[0]['id'] if match else None,'district':match[0]['name'] if match else None})
# Retain precise geometry for point classification; simplify only display paths.
for row in allrows:
 rings=row.pop('outer')+row.pop('inner');row['rings']=[rdp(r,.00016) for r in rings]
 row['bounds']=[min(p[0] for r in rings for p in r),min(p[1] for r in rings for p in r),max(p[0] for r in rings for p in r),max(p[1] for r in rings for p in r)]
payload={'source':'https://www.openstreetmap.org/copyright','license':'ODbL-1.0','data_timestamp':data['osm3s']['timestamp_osm_base'],'districts':sorted(allrows,key=lambda x:x['name'])}
(root/'apps/web/lib/moscowDistrictGeometry.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')))
(root/'data/moscow_venue_districts.json').write_text(json.dumps({'boundary_source':payload['source'],'boundary_timestamp':payload['data_timestamp'],'coordinate_source':'Individual SpeedRent source cards, data-coords attribute','checked_at':'2026-09-11','items':enriched},ensure_ascii=False,indent=2))
print('Districts',len(allrows),'coordinates',sum('lat'in p for p in enriched),'district matches',sum(bool(p.get('district_id'))for p in enriched))
