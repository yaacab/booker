import assert from 'node:assert/strict';
import test from 'node:test';
import { installSceneRecovery } from './scene01Recovery';
class Page extends EventTarget {
 values = new Map<string,string>(); blocked = false;
 get sessionStorage() {
  if (this.blocked) throw new Error('Storage unavailable');
  return {getItem:(key:string)=>this.values.get(key)??null,setItem:(key:string,value:string)=>{this.values.set(key,value);},removeItem:(key:string)=>{this.values.delete(key);}};
 }
 show(persisted:boolean) {this.dispatchEvent(Object.assign(new Event('pageshow'),{persisted}));}
}
test('cached page returns a visible scene instead of the faded departure frame',()=>{
 const page=new Page(),recovered:string[]=[]; installSceneRecovery(page,mode=>recovered.push(mode));page.show(true);assert.deepEqual(recovered,['ready']);
});
test('back after a role choice restores role cards, including repeated returns',()=>{
 const page=new Page(),recovered:string[]=[];const r=installSceneRecovery(page,mode=>recovered.push(mode));r.markRoleNavigation();page.show(true);page.show(true);assert.deepEqual(recovered,['reg','reg']);
});
test('fresh document restores role choice saved by previous document',()=>{
 const page=new Page();installSceneRecovery(page,()=>{}).markRoleNavigation();const recovered:string[]=[];installSceneRecovery(page,mode=>recovered.push(mode));assert.deepEqual(recovered,['reg']);
});
test('ordinary initial visit preserves full intro',()=>{
 const page=new Page(),recovered:string[]=[];installSceneRecovery(page,mode=>recovered.push(mode));page.show(false);assert.deepEqual(recovered,[]);
});
test('explicit replay clears remembered role selection',()=>{
 const page=new Page(),recovered:string[]=[];const r=installSceneRecovery(page,mode=>recovered.push(mode));r.markRoleNavigation();r.clearReturn();page.show(true);assert.deepEqual(recovered,['ready']);const next:string[]=[];installSceneRecovery(page,mode=>next.push(mode));assert.deepEqual(next,[]);
});
test('private browsing storage failures cannot leave back navigation blank',()=>{
 const page=new Page();page.blocked=true;const recovered:string[]=[];const r=installSceneRecovery(page,mode=>recovered.push(mode));r.markRoleNavigation();page.show(true);r.clearReturn();page.show(true);assert.deepEqual(recovered,['reg','ready']);
});
test('unmount removes restoration listener',()=>{
 const page=new Page(),recovered:string[]=[];const r=installSceneRecovery(page,mode=>recovered.push(mode));r.dispose();page.show(true);assert.deepEqual(recovered,[]);
});
