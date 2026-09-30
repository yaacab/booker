import test from "node:test";
import assert from "node:assert/strict";
import { createFavoriteReader } from "./favoriteReads";

test("a catalog shares one favorite read across 60 cards and refreshes on next visit",async()=>{
  let calls=0;
  const read=createFavoriteReader(async()=>{calls++;return [{id:"f",target_type:"artist" as const,target_id:"a"}]},()=>"user/org");
  const items=await Promise.all(Array.from({length:60},()=>read()));
  assert.equal(calls,1);assert.ok(items.every(rows=>rows[0].id==="f"));
  await read();assert.equal(calls,2);
});
test("simultaneous favorite reads are isolated across organizations and sessions",async()=>{
  let scope="session-a/org-a",calls=0;
  const read=createFavoriteReader(async()=>{calls++;return [{id:scope,target_type:"artist" as const,target_id:"a"}]},()=>scope);
  const first=read();scope="session-a/org-b";const second=read();scope="session-b/org-b";const third=read();
  assert.notEqual(first,second);assert.notEqual(second,third);
  const results=await Promise.all([first,second,third]);assert.equal(calls,3);
  assert.deepEqual(results.map(rows=>rows[0].id),["session-a/org-a","session-a/org-b","session-b/org-b"]);
});
test("failed favorite loads are retried",async()=>{
  let calls=0;
  const read=createFavoriteReader(async()=>{if(++calls===1)throw Error("offline");return []},()=>"user/org");
  await assert.rejects(read());assert.deepEqual(await read(),[]);assert.equal(calls,2);
});
