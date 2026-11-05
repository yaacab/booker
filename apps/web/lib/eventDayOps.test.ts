import test from "node:test";
import assert from "node:assert/strict";
import { buildNextSteps, isClosedRequest, needsReplacement } from "./eventDayOps";

test("a cancelled booking restores the position and asks for replacement",()=>{
  const request={id:"cancelled",status:"Cancelled",requirement_id:"host",booking_id:"old-booking"};
  assert.equal(isClosedRequest(request),false);
  const [step]=buildNextSteps([{id:"host",category_code:"host",qty:1}],[request],()=>"Ведущий");
  assert.equal(step.openSlots,1);
  assert.equal(step.blocker,"no_request");
  assert.equal(needsReplacement(step),true);
});

test("multiple performers retain unfilled quantity and pending responses",()=>{
  const [step]=buildNextSteps([{id:"dj",category_code:"dj",qty:2}],[{id:"chosen",status:"Confirmed",requirement_id:"dj",booking_id:"booking"},{id:"waiting",status:"RequestSent",requirement_id:"dj"}],()=>"Диджей");
  assert.equal(step.filled,1);
  assert.equal(step.openSlots,1);
  assert.equal(step.blocker,"no_offer");
});
