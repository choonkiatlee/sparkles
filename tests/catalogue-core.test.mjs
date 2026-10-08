import test from "node:test";
import assert from "node:assert/strict";
import {MAX_SELECTION,validateIndex,visibleRows,priceText,dimensionsText,selectionFromSearch,selectionSearch,toggleSelection} from "../catalogue/core.mjs";

const rows = [
 {id:"igi-lg756520111",lab:"IGI",report_number:"LG756520111",retailer:"www.qualitydiamonds.co.uk",carat:"2.59",clarity:"VVS1",colour:"F",dimensions:[7.58,7.55,4.88],price:"685.00",currency:"GBP",retrieval_status:"partial"},
 {id:"igi-lg816611062",lab:"IGI",report_number:"LG816611062",retailer:"diyona.com",carat:"2.69",clarity:"VVS1",colour:"D",dimensions:[7.61,7.53,5.05],price:"749.77",currency:"USD",retrieval_status:"complete"}
];
test("v1 index rejects unsupported format and duplicate identities",()=>{
  assert.equal(validateIndex({schema:"sparkles-diamond-index/1",diamonds:rows}).length,2);
  assert.throws(()=>validateIndex({schema:"wrong",diamonds:rows}));
  assert.throws(()=>validateIndex({schema:"sparkles-diamond-index/1",diamonds:[rows[0],rows[0]]}));
});
test("search, filter and carat sort are deterministic",()=>{
  assert.deepEqual(visibleRows(rows,{search:"diyona"}).map(r=>r.id),[rows[1].id]);
  assert.deepEqual(visibleRows(rows,{status:"partial"}).map(r=>r.id),[rows[0].id]);
  assert.deepEqual(visibleRows(rows,{sort:"carat"}).map(r=>r.id),[rows[0].id,rows[1].id]);
  assert.deepEqual(visibleRows(rows,{search:"not-found"}),[]);
});
test("price order groups currency instead of pretending currency conversion",()=>{
  const sorted = visibleRows(rows,{sort:"price"});
  assert.deepEqual(sorted.map(r=>r.currency),["GBP","USD"]);
  assert.match(priceText(rows[0]),/£685/);
  assert.match(priceText(rows[1]),/\$749/);
  assert.equal(priceText({...rows[0],price:null}),"Price unavailable");
  assert.equal(priceText({...rows[0],price:"100",currency:null}),"100.00 (currency unknown)");
});
test("dimensions and null fields remain honest",()=>{
  assert.equal(dimensionsText(rows[0]),"7.58 × 7.55 × 4.88 mm");
  assert.equal(dimensionsText({dimensions:null}),"Unknown");
});
test("selection dedupes URL IDs, bounds at five, keeps bookmarkable compare state",()=>{
  const ids=new Set(rows.map(r=>r.id));
  const state=selectionFromSearch("?selected="+rows[0].id+","+rows[1].id+","+rows[1].id+",fake&compare=1",ids);
  assert.deepEqual(state.selected,[rows[0].id,rows[1].id]);
  assert.equal(state.comparing,true);
  assert.deepEqual(toggleSelection(state.selected,rows[0].id),[rows[1].id]);
  assert.deepEqual(toggleSelection([1,2,3,4,5],6),[1,2,3,4,5]);
  const query=selectionSearch("?utm_source=test",state.selected,true);
  assert.equal(selectionFromSearch("?"+query,ids).comparing,true);
  assert.match(query,/utm_source=test/);
  assert.equal(MAX_SELECTION,5);
});
