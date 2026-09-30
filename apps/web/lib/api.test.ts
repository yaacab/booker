import test from "node:test";
import assert from "node:assert/strict";
import { apiErrorMessage, clientEventFetchInit } from "./api";

test("clientEventFetchInit uses keepalive for navigation-safe analytics", () => {
  const init = clientEventFetchInit('{"name":"search.performed"}', {
    "Content-Type": "application/json",
  });
  assert.equal(init.method, "POST");
  assert.equal(init.keepalive, true);
});

test("API errors preserve actionable conflicts without exposing HTML or server exceptions", () => {
  assert.equal(apiErrorMessage(409, "Дата уже занята"), "Дата уже занята");
  assert.equal(apiErrorMessage(403, "Недостаточно прав"), "Недостаточно прав");
  assert.doesNotMatch(apiErrorMessage(404, "<!DOCTYPE html><h1>Proxy error</h1>"), /DOCTYPE|Proxy/);
  assert.doesNotMatch(apiErrorMessage(500, "Database exception: private@example.test"), /Database|private/);
  assert.doesNotMatch(apiErrorMessage(422, [{ msg: "Invalid", input: "private@example.test" }]), /private/);
  assert.ok(apiErrorMessage(200, undefined));
});

test("demo sessions use the isolated API and leave a real session intact", async () => {
 const {apiBase,getToken,getActiveOrg,setActiveOrg,setToken}=await import("./api");
 const memory=()=>{const m=new Map<string,string>();return {getItem:(k:string)=>m.get(k)||null,setItem:(k:string,v:string)=>m.set(k,v),removeItem:(k:string)=>m.delete(k)}};
 const local=memory(),session=memory();
 const original=Object.fromEntries(["window","localStorage","sessionStorage"].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 try{Object.defineProperty(globalThis,"window",{configurable:true,value:{}});Object.defineProperty(globalThis,"localStorage",{configurable:true,value:local});Object.defineProperty(globalThis,"sessionStorage",{configurable:true,value:session});
 local.setItem("booker.token","real-token");local.setItem("booker.org","real-org");session.setItem("booker.demo.token","demo-token");
 assert.equal(apiBase(),"/development-api");assert.equal(getToken(),"demo-token");assert.equal(getActiveOrg(),null);
 setActiveOrg("demo-org");assert.equal(getActiveOrg(),"demo-org");assert.equal(local.getItem("booker.org"),"real-org");
 setToken(null);assert.equal(getToken(),"real-token");assert.equal(getActiveOrg(),"real-org");assert.equal(session.getItem("booker.demo.token"),null);
 }finally{for(const key of Object.keys(original)){if(original[key])Object.defineProperty(globalThis,key,original[key]!);else Reflect.deleteProperty(globalThis,key)}}
});
