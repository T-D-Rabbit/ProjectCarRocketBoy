// Headless test of RocketBoy_Simulator.html: fake DOM, synthetic key presses, checks the controls end to end.
//   node simulation/test_simulator_ui.js      (run from the repository root or from simulation/)
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(require('path').join(__dirname, '..', 'RocketBoy_Simulator.html'), 'utf8');
let script = html.match(/<script>([\s\S]*)<\/script>/)[1];
script += '\n;globalThis.__t = {sim, get s(){return {mode, ulC, urC, routeIdx}}, hist, trail, bank: sim.bank, cv, img, setSoft(v){soft=v}};';
const els = {};
const ctxStub = new Proxy({}, { get: (t, k) => {
  if (k === 'createImageData') return (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h });
  if (k === 'measureText') return () => ({ width: 100 });
  if (k in t) return t[k];
  return () => {};
}, set: (t, k, v) => { t[k] = v; return true; } });
function el(id) {
  if (!els[id]) els[id] = { id, style: {}, classList: { add(){}, remove(){}, toggle(){} }, innerHTML: '', textContent: '', checked: /^(g1|soft|chase)$/.test(id), value: id === 'duty' ? '0.6' : '1',
    width: 1100, height: 620, getContext: () => ctxStub, addEventListener(){}, setPointerCapture(){}, appendChild(){}, focus(){}, children: [] };
  return els[id];
}
const listeners = {}; let rafCb = null; let nowT = 0;
const sandbox = { document: { getElementById: el, createElement: () => el('_c' + Math.random()) }, performance: { now: () => nowT },
  window: { addEventListener: (n, f) => { listeners[n] = f; } }, requestAnimationFrame: f => { rafCb = f; }, console, Math, Float32Array, Uint32Array, Uint8ClampedArray, JSON };
vm.createContext(sandbox);
vm.runInContext(script, sandbox);
const T = sandbox.__t;
function frames(n, ms) { for (let i = 0; i < n; i++) { nowT += ms || 16.7; const f = rafCb; f(nowT); } }
function key(k, down) { (listeners[down ? 'keydown' : 'keyup'])({ key: k, target: { tagName: 'CANVAS' }, preventDefault(){} }); }
const out = {};
frames(5);
key('w', true); frames(120); key('w', false);
out.drive = { v: +T.sim.v.toFixed(3), x: +T.sim.x.toFixed(3), il: +T.sim.il.toFixed(3), hist: T.hist.length, trail: T.trail.length };
frames(200);
out.coast = +T.sim.v.toFixed(3);
const th0 = T.sim.th; key('a', true); frames(60); key('a', false); out.turnLeft_deg = +((T.sim.th - th0) * 180 / Math.PI).toFixed(1);
key('2', true); key('2', false); out.groups = T.bank.groups.slice();
key('r', true); key('r', false); out.reset = { t: +T.sim.t.toFixed(3), x: T.sim.x };
// jam + only SW1 -> overload
el('jam').checked = true; el('jam').onchange({ target: el('jam') });
key('w', true); frames(30); key('w', false);
out.jam = { il: +T.sim.il.toFixed(2), worst: +Math.max(...T.bank.stat.A, ...T.bank.stat.B).toFixed(2) };
el('jam').checked = false; el('jam').onchange({ target: el('jam') });
// hard-coded route (reset first, groups: SW1 only to match the python reference)
key('r', true); key('r', false);
el('g2').checked = false; el('g2').onchange();
el('bRoute').onclick();
let n = 0; while (T.s.mode === 'route' && n < 3000) { frames(1); n++; }
out.route = { frames: n, x: +T.sim.x.toFixed(5), y: +T.sim.y.toFixed(5), th: +T.sim.th.toFixed(5), t: +T.sim.t.toFixed(2) };
frames(10);
console.log(JSON.stringify(out));
const ok = out.drive.v > 0.5 && out.drive.il > 0.2 && out.coast < 0.05 && out.turnLeft_deg > 20 && out.groups[1] === true &&
  out.reset.t === 0 && out.reset.x === 0 && out.jam.il > 1.0 && T.s.mode === 'manual' && Math.abs(out.route.t - 15.2) < 0.3 &&
  Math.hypot(out.route.x, out.route.y) < 0.2;
console.log(ok ? 'UI TEST PASS' : 'UI TEST FAIL'); process.exit(ok ? 0 : 1);
