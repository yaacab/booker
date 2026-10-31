import test from 'node:test';
import assert from 'node:assert/strict';
import { fromVisual, toVisual } from './v5Adapter';
import { EMPTY_DRAFT } from './types';
test('v5 roundtrip keeps real resource IDs, existing end time and rider notes', () => {
 const base={...EMPTY_DRAFT,title:'Наш праздник',talentIds:['real-artist'],venueId:'real-venue',endsAt:'23:45',version:9};
 const visual={...toVisual(base),dateISO:'2027-02-11',date:11,time:'19:15',city:'Казань',format:'birthday',guests:37,budget:123456,rider:{matches:0,open:1,requirements:['Звук'],notes:'Монтаж в 16:00'}};
 const next=fromVisual(base,visual);
 assert.equal(next.title,'Наш праздник');assert.equal(next.kind,'День рождения');assert.equal(next.endsAt,'23:45');
 assert.deepEqual(next.talentIds,['real-artist']);assert.equal(next.venueId,'real-venue');assert.equal(next.startsAt,'19:15');
 assert.deepEqual(toVisual(next).rider,visual.rider);assert.equal(toVisual(next).budget,123456);
});
test('catalog additions after a saved v5 draft override stale visual IDs', () => {
 const old=fromVisual(EMPTY_DRAFT,{...toVisual(EMPTY_DRAFT),artists:['old'],venue:'old-venue',artistsDeferred:true,venueDeferred:true});
 const next=toVisual({...old,talentIds:['server-new'],venueId:'server-venue'});
 assert.deepEqual(next.artists,['server-new']);assert.equal(next.venue,'server-venue');
});
test('fresh draft does not invent a budget or selected providers',()=>{
 const draft=toVisual(EMPTY_DRAFT);assert.equal(draft.budget,null);assert.deepEqual(draft.artists,[]);assert.equal(draft.venue,null);
});

test('saving rider first does not silently fill format and guests',()=>{const v=toVisual(EMPTY_DRAFT);const d=fromVisual(EMPTY_DRAFT,{...v,rider:{matches:0,open:0,requirements:[],notes:'Звук'}});const next=toVisual(d);assert.equal(next.format,null);assert.equal(next.guests,null);});
