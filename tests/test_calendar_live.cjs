const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ctx = vm.createContext({window:{addEventListener(){}}, Intl, Date, Map, URLSearchParams});
vm.runInContext(fs.readFileSync(__dirname+'/../web/app.js','utf8').split('setInterval(() => { renderClock();')[0], ctx);
test('timed pill activates at start and stops at end', () => {
  assert.equal(typeof ctx.eventLive, 'function');
  const ev={start:'2026-10-30T10:00:00-05:00',end:'2026-10-30T11:00:00-05:00'};
  for(const [time,expected] of [['09:59:59',false],['10:00:00',true],['10:30:00',true],['11:00:00',false]])
    assert.equal(ctx.eventLive(ev,'2026-10-30',new Date(`2026-10-30T${time}-05:00`)),expected,time);
  assert.equal(ctx.eventLive({start:'invalid'},'2026-10-30',new Date()),false);
});
test('sun phase is day from sunrise until sunset', () => {
  assert.equal(typeof ctx.sunIsUp, 'function');
  const sun={sunrise:'2026-10-30T07:34:00-05:00',sunset:'2026-10-30T18:37:00-05:00'};
  for (const [time,expected] of [['07:33:59',false],['07:34:00',true],['12:00:00',true],['18:36:59',true],['18:37:00',false],['23:00:00',false]])
    assert.equal(ctx.sunIsUp(sun,new Date(`2026-10-30T${time}-05:00`)),expected,time);
  assert.equal(ctx.sunIsUp(null,new Date()),null);
});
test('all-day follows Chicago midnight, not UTC or the browser timezone', () => {
  const ev={allDay:true};
  for (const [instant,expected] of [
    ['2026-10-30T04:59:59Z',false],['2026-10-30T05:00:00Z',true],
    ['2026-10-31T04:59:59Z',true],['2026-10-31T05:00:00Z',false]
  ]) assert.equal(ctx.eventLive(ev,'2026-10-30',new Date(instant)),expected,instant);
  assert.equal(ctx.eventLive(ev,'2026-10-31',new Date('2026-10-30T18:00:00Z')),false);
});
