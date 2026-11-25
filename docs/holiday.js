(function () {
	'use strict';

	var KEY = 'rhh-holiday-override';
	var REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

	/* ------------------------------------------------------------------ *
	 * Date helpers
	 * ------------------------------------------------------------------ */
	function midnight(d) { return new Date(d.getFullYear(), d.getMonth(), d.getDate()); }
	function addDays(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }
	function inDays(t, a, b) {
		var T = midnight(t).getTime();
		return T >= midnight(a).getTime() && T <= midnight(b).getTime();
	}

	// Anonymous Gregorian algorithm (Meeus/Jones/Butcher). Returns Easter Sunday.
	function easter(y) {
		var a = y % 19, b = Math.floor(y / 100), c = y % 100;
		var d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
		var g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
		var i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7;
		var m = Math.floor((a + 11 * h + 22 * l) / 451);
		var month = Math.floor((h + l - 7 * m + 114) / 31); // 3=Mar, 4=Apr
		var day = ((h + l - 7 * m + 114) % 31) + 1;
		return new Date(y, month - 1, day);
	}

	/* ------------------------------------------------------------------ *
	 * The calendar - ordered by priority (specific windows before Autumn).
	 * ------------------------------------------------------------------ */
	function md(t) { return (t.getMonth() + 1) * 100 + t.getDate(); }

	var THEMES = [
		{ id: 'newyear', night: true,   // Dec 31 - Jan 2
			match: function (t) { return (t.getMonth() === 11 && t.getDate() >= 31) || (t.getMonth() === 0 && t.getDate() <= 2); },
			fx: { kind: 'fireworks', colors: ['#ffd700', '#ffffff', '#c0c0c0', '#ffe89a', '#f5b301'] } },

		{ id: 'easter',                 // Easter weekend (computed)
			match: function (t, y) { return inDays(t, addDays(easter(y), -2), addDays(easter(y), 1)); },
			fx: { kind: 'crosses', colors: ['#caa64a', '#dcbe6a', '#efe3b0', '#ffffff'] } },

		{ id: 'midsummer',              // Jun 21 - 24
			match: function (t) { return t.getMonth() === 5 && t.getDate() >= 21 && t.getDate() <= 24; },
			fx: { kind: 'floral', colors: ['#ffe14d', '#ffffff', '#f4c430', '#6ab04c', '#8bd450'] } },

		{ id: 'independence',           // Jul 1 - 5
			match: function (t) { return t.getMonth() === 6 && t.getDate() >= 1 && t.getDate() <= 5; },
			fx: { kind: 'fireworks', colors: ['#e63946', '#ffffff', '#4361ee', '#a8dadc', '#f1faee'] } },

		{ id: 'halloween', night: true, // Oct 24 - 31
			match: function (t) { return t.getMonth() === 9 && t.getDate() >= 24 && t.getDate() <= 31; },
			fx: { kind: 'bats', colors: ['#e8720c', '#d1571a', '#a86cd8', '#c98a2b'] } },

		{ id: 'obon', night: true,      // Aug 13 - 16
			match: function (t) { return t.getMonth() === 7 && t.getDate() >= 13 && t.getDate() <= 16; },
			fx: { kind: 'lanterns', colors: ['#ff8a3c', '#ffb347', '#ff6b4a', '#ffd27a', '#e8552e'] } },

		{ id: 'autumn',                 // Sep 22 - Nov 30 (fallback)
			match: function (t) { var m = md(t); return m >= 922 && m <= 1130; },
			fx: { kind: 'leaves', colors: ['#c1440e', '#e8720c', '#b5651d', '#8a5a24', '#d99a2b'] } },

		{ id: 'christmas', night: true, // Dec 1 - 26
			match: function (t) { return t.getMonth() === 11 && t.getDate() >= 1 && t.getDate() <= 26; },
			fx: { kind: 'snow', colors: ['#ffffff', '#eaf6ff', '#cfe8ff'], overlays: ['lights'] } }
	];

	function pickAuto(today) {
		var y = today.getFullYear();
		for (var i = 0; i < THEMES.length; i++) {
			if (THEMES[i].match(today, y)) return THEMES[i];
		}
		return null;
	}

	function byId(id) {
		for (var i = 0; i < THEMES.length; i++) if (THEMES[i].id === id) return THEMES[i];
		return null;
	}

	/* ------------------------------------------------------------------ *
	 * Small utils
	 * ------------------------------------------------------------------ */
	function rand(a, b) { return a + Math.random() * (b - a); }
	function pick(arr) { return arr[(Math.random() * arr.length) | 0]; }

	/* ------------------------------------------------------------------ *
	 * Effect engine
	 * ------------------------------------------------------------------ */
	var fx = null; // active effect state

	function teardown() {
		if (fx) {
			if (fx.raf) cancelAnimationFrame(fx.raf);
			window.removeEventListener('resize', fx.onResize);
			document.removeEventListener('visibilitychange', fx.onVis);
			fx = null;
		}
		// remove by id (also covers the reduced-motion path, where fx is null)
		var el = document.getElementById('holiday-fx');
		if (el) el.parentNode.removeChild(el);
	}

	function buildOverlay(theme, animated) {
		var root = document.createElement('div');
		root.id = 'holiday-fx';
		root.setAttribute('aria-hidden', 'true');
		if (!animated) root.className = 'hx-static';

		var top = document.createElement('div');
		top.className = 'hx-top';
		root.appendChild(top);

		var overlays = (theme.fx.overlays || []);

		// String lights (Christmas) - colored bulbs across the top.
		if (overlays.indexOf('lights') !== -1) {
			top.classList.add('hx-lights');
			layoutBulbs(top);
		}
		var canvas = null;
		if (animated && theme.fx.kind) {
			canvas = document.createElement('canvas');
			canvas.id = 'holiday-canvas';
			root.appendChild(canvas);
		}

		document.body.appendChild(root);
		return { root: root, canvas: canvas };
	}

	function apply(theme) {
		teardown();
		var html = document.documentElement;
		if (!theme) { html.removeAttribute('data-theme'); html.removeAttribute('data-night'); return; }
		html.setAttribute('data-theme', theme.id);
		if (theme.night) html.setAttribute('data-night', ''); else html.removeAttribute('data-night');

		var animated = !REDUCED;
		var built = buildOverlay(theme, animated);
		if (!animated || !built.canvas) return; // recolor + static decor only

		startCanvas(theme, built.canvas, built.root);
	}

	function startCanvas(theme, canvas, root) {
		var ctx = canvas.getContext('2d');
		var kind = theme.fx.kind;
		var colors = theme.fx.colors;
		var W = 0, H = 0, dpr = 1;
		var parts = [];
		var fwState = { rockets: [], sparks: [], timer: 0.4 };

		function size() {
			dpr = Math.min(2, window.devicePixelRatio || 1);
			W = window.innerWidth; H = window.innerHeight;
			canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
			canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		}
		size();
		if (kind !== 'fireworks') parts = populate(kind, colors, W, H);

		var last = 0, running = true;
		function frame(ts) {
			if (!running) return;
			if (!last) last = ts;
			var dt = Math.min(0.05, (ts - last) / 1000); last = ts;
			ctx.clearRect(0, 0, W, H);
			if (kind === 'fireworks') stepFireworks(ctx, fwState, colors, dt, W, H);
			else { for (var i = 0; i < parts.length; i++) { stepPart(parts[i], dt, W, H); drawPart(ctx, parts[i]); } }
			fx.raf = requestAnimationFrame(frame);
		}

		fx = {
			root: root, raf: null,
			onResize: function () {
				size();
				if (kind !== 'fireworks') parts = populate(kind, colors, W, H);
				var lights = root.querySelector('.hx-lights');
				if (lights) layoutBulbs(lights);
			},
			onVis: function () {
				running = !document.hidden;
				if (running) { last = 0; fx.raf = requestAnimationFrame(frame); }
			}
		};
		window.addEventListener('resize', fx.onResize);
		document.addEventListener('visibilitychange', fx.onVis);
		fx.raf = requestAnimationFrame(frame);
	}

	/* ---------- particles ---------- */
	function populate(kind, colors, W, H) {
		var out = [];
		var scale = Math.min(1.5, Math.max(0.45, (W * H) / (1280 * 800)));
		var base = { snow: 90, leaves: 42, petals: 46, floral: 46, crosses: 40, lanterns: 0, bats: 0 };
		var n = Math.round((base[kind] || 40) * scale);
		for (var i = 0; i < n; i++) out.push(mkFalling(kind, colors, W, H));
		if (kind === 'bats') {
			var nb = Math.max(4, Math.round(7 * scale)), nl = Math.round(26 * scale);
			for (var b = 0; b < nb; b++) out.push(mkBat(colors, W, H));
			for (var l = 0; l < nl; l++) out.push(mkFalling('leaves', colors, W, H));
		}
		if (kind === 'lanterns') {
			var nLan = Math.round(24 * scale);
			for (var m = 0; m < nLan; m++) out.push(mkLantern(colors, W, H));
		}
		return out;
	}

	function mkFalling(kind, colors, W, H) {
		var typeByKind = { snow: 'snow', leaves: 'leaf', petals: 'petal', crosses: 'cross' };
		var type = typeByKind[kind];
		// Midsummer: flower crowns (hero) + wildflowers + birch leaves
		if (kind === 'floral') type = pick(['wreath', 'flower', 'flower', 'leaf']);
		var size = type === 'snow' ? rand(2, 5)
			: type === 'wreath' ? rand(11, 19)
			: type === 'leaf' ? rand(9, 17)
			: type === 'flower' ? rand(9, 15)
			: type === 'cross' ? rand(9, 16)
			: rand(7, 13);
		// leaves -> green, flowers -> white/yellow/blue (wreaths draw their own)
		var color = pick(colors);
		if (kind === 'floral') {
			if (type === 'leaf') color = pick(['#6ab04c', '#7ec850', '#4e9c3a']);
			else if (type === 'flower') color = pick(['#ffffff', '#ffe14d', '#7aa8e0']);
		}
		// crosses stay near-upright - a spinning cross can read inverted
		var upright = type === 'cross';
		return {
			type: type,
			x: Math.random() * W,
			y: rand(-H, 0),
			vy: type === 'snow' ? rand(20, 55) : type === 'cross' ? rand(28, 62) : rand(35, 90),
			vx: rand(-14, 14),
			sway: rand(10, 34), swaySpeed: rand(0.6, 1.6), phase: Math.random() * 6.28,
			rot: upright ? rand(-0.12, 0.12) : Math.random() * 6.28,
			vr: upright ? 0 : rand(-1.4, 1.4),
			size: size, color: color,
			alpha: type === 'snow' ? rand(0.5, 0.95) : rand(0.75, 1)
		};
	}

	function mkLantern(colors, W, H) {
		var y = rand(H * 0.5, H * 0.97);       // afloat on the lower "water"
		return {
			type: 'lantern',
			x: Math.random() * W,
			y: y, baseY: y,
			vx: rand(9, 24),                   // drifts downstream
			bob: rand(3, 8), bobSpeed: rand(0.4, 1.0), phase: Math.random() * 6.28,
			size: rand(11, 20), color: pick(colors), alpha: rand(0.85, 1)
		};
	}

	function mkBat(colors, W, H) {
		var dir = Math.random() < 0.5 ? 1 : -1;
		return {
			type: 'bat', dir: dir,
			x: dir > 0 ? rand(-60, -20) : rand(W + 20, W + 60),
			y: rand(30, H * 0.55),
			vx: dir * rand(55, 95),
			bob: rand(12, 30), bobSpeed: rand(1, 2), phase: Math.random() * 6.28,
			flap: 0, flapSpeed: rand(6, 11),
			size: rand(14, 26), color: pick(colors), alpha: rand(0.7, 0.95)
		};
	}

	function stepPart(p, dt, W, H) {
		if (p.type === 'lantern') {
			p.phase += p.bobSpeed * dt;
			p.x += p.vx * dt;
			p.y = p.baseY + Math.sin(p.phase) * p.bob;
			if (p.x > W + 40) { p.x = -40; p.baseY = rand(H * 0.5, H * 0.97); }
			return;
		}
		if (p.type === 'bat') {
			p.phase += p.bobSpeed * dt; p.flap += p.flapSpeed * dt;
			p.x += p.vx * dt; p.y += Math.sin(p.phase) * p.bob * dt;
			if (p.dir > 0 && p.x > W + 60) { p.x = -60; p.y = rand(30, H * 0.55); }
			if (p.dir < 0 && p.x < -60) { p.x = W + 60; p.y = rand(30, H * 0.55); }
			return;
		}
		p.phase += p.swaySpeed * dt;
		p.y += p.vy * dt;
		p.x += (p.vx + Math.sin(p.phase) * p.sway) * dt;
		p.rot += p.vr * dt;
		if (p.y > H + 26) { p.y = -22; p.x = Math.random() * W; }
		if (p.x < -30) p.x = W + 20; else if (p.x > W + 30) p.x = -20;
	}

	function drawPart(ctx, p) {
		ctx.save();
		ctx.globalAlpha = p.alpha;
		ctx.translate(p.x, p.y);
		if (p.type !== 'snow' && p.type !== 'bat' && p.type !== 'lantern') ctx.rotate(p.rot);
		ctx.fillStyle = p.color;
		switch (p.type) {
			case 'snow':
				ctx.beginPath(); ctx.arc(0, 0, p.size, 0, 6.283); ctx.fill(); break;
			case 'leaf':
				ctx.beginPath();
				ctx.ellipse(0, 0, p.size * 0.55, p.size, 0, 0, 6.283); ctx.fill();
				ctx.strokeStyle = 'rgba(0,0,0,0.22)'; ctx.lineWidth = Math.max(0.6, p.size * 0.08);
				ctx.beginPath(); ctx.moveTo(0, -p.size); ctx.lineTo(0, p.size); ctx.stroke();
				break;
			case 'petal':
				ctx.beginPath(); ctx.ellipse(0, 0, p.size * 0.5, p.size, 0, 0, 6.283); ctx.fill(); break;
			case 'cross':
				drawCross(ctx, p.size, p.color, p.alpha); break;
			case 'wreath':
				drawWreath(ctx, p.size); break;
			case 'flower':
				drawFlower(ctx, p.size, p.color); break;
			case 'bat':
				drawBat(ctx, p.size, p.color, Math.sin(p.flap)); break;
			case 'lantern':
				drawLantern(ctx, p.size, p.color, p.alpha); break;
		}
		ctx.restore();
	}

	// Obon paper lantern
	function drawLantern(ctx, s, color, alpha) {
		ctx.globalAlpha = alpha;
		ctx.shadowColor = color;
		ctx.shadowBlur = s * 0.9;
		ctx.fillStyle = color;
		ctx.beginPath();
		ctx.ellipse(0, 0, s * 0.6, s * 0.8, 0, 0, 6.283);
		ctx.fill();
		ctx.shadowBlur = 0;
		ctx.globalAlpha = alpha * 0.7;
		ctx.fillStyle = '#fff2c2';
		ctx.beginPath();
		ctx.ellipse(0, 0, s * 0.3, s * 0.42, 0, 0, 6.283);
		ctx.fill();
		ctx.globalAlpha = alpha;
		ctx.fillStyle = 'rgba(38,22,12,0.9)';
		rr(ctx, -s * 0.26, -s * 0.94, s * 0.52, s * 0.16, s * 0.05);
		rr(ctx, -s * 0.26, s * 0.78, s * 0.52, s * 0.16, s * 0.05);
	}

	function rr(ctx, x, y, w, h, r) {
		ctx.beginPath();
		ctx.moveTo(x + r, y);
		ctx.arcTo(x + w, y, x + w, y + h, r);
		ctx.arcTo(x + w, y + h, x, y + h, r);
		ctx.arcTo(x, y + h, x, y, r);
		ctx.arcTo(x, y, x + w, y, r);
		ctx.closePath();
		ctx.fill();
	}

	// Latin cross with radiating light rays
	function drawCross(ctx, s, color, alpha) {
		ctx.globalAlpha = alpha * 0.4;
		ctx.strokeStyle = color;
		ctx.lineWidth = Math.max(0.7, s * 0.08);
		ctx.beginPath();
		for (var i = 0; i < 8; i++) {
			var a = i * Math.PI / 4;
			ctx.moveTo(Math.cos(a) * s * 0.6, Math.sin(a) * s * 0.6);
			ctx.lineTo(Math.cos(a) * s * 1.25, Math.sin(a) * s * 1.25);
		}
		ctx.stroke();
		ctx.globalAlpha = alpha;
		ctx.fillStyle = color;
		var w = s * 0.28;
		rr(ctx, -w / 2, -s * 0.74, w, s * 1.48, w * 0.35);
		rr(ctx, -s * 0.5, -s * 0.32, s, w, w * 0.35);
	}

	// Midsummer flower crown: greenery ring + wildflower dots
	function drawWreath(ctx, s) {
		ctx.strokeStyle = '#5a9e3f';
		ctx.lineWidth = Math.max(1.4, s * 0.2);
		ctx.beginPath();
		ctx.arc(0, 0, s * 0.7, 0, 6.283);
		ctx.stroke();
		var dots = ['#ffffff', '#ffe14d', '#7aa8e0', '#ffffff'];
		for (var i = 0; i < 7; i++) {
			var a = i * (6.283 / 7);
			ctx.fillStyle = dots[i % dots.length];
			ctx.beginPath();
			ctx.arc(Math.cos(a) * s * 0.7, Math.sin(a) * s * 0.7, s * 0.17, 0, 6.283);
			ctx.fill();
		}
	}

	function drawFlower(ctx, s, color) {
		ctx.fillStyle = color;
		for (var i = 0; i < 5; i++) {
			ctx.save(); ctx.rotate(i * 2 * Math.PI / 5);
			ctx.beginPath(); ctx.ellipse(0, -s * 0.5, s * 0.3, s * 0.5, 0, 0, 6.283); ctx.fill();
			ctx.restore();
		}
		ctx.fillStyle = '#f6c445';
		ctx.beginPath(); ctx.arc(0, 0, s * 0.26, 0, 6.283); ctx.fill();
	}

	function drawBat(ctx, s, color, flap) {
		ctx.fillStyle = color;
		var wing = s * (0.5 + 0.28 * flap);
		ctx.beginPath();
		ctx.moveTo(0, 0);
		ctx.quadraticCurveTo(-s * 0.5, -wing, -s, -s * 0.1);
		ctx.quadraticCurveTo(-s * 0.6, wing * 0.35, -s * 0.28, s * 0.18);
		ctx.quadraticCurveTo(-s * 0.14, s * 0.05, 0, s * 0.28);
		ctx.quadraticCurveTo(s * 0.14, s * 0.05, s * 0.28, s * 0.18);
		ctx.quadraticCurveTo(s * 0.6, wing * 0.35, s, -s * 0.1);
		ctx.quadraticCurveTo(s * 0.5, -wing, 0, 0);
		ctx.fill();
		ctx.beginPath(); ctx.ellipse(0, s * 0.02, s * 0.16, s * 0.24, 0, 0, 6.283); ctx.fill();
	}

	/* ---------- fireworks ---------- */
	function stepFireworks(ctx, st, colors, dt, W, H) {
		st.timer -= dt;
		if (st.timer <= 0) {
			st.rockets.push({
				x: rand(W * 0.15, W * 0.85), y: H + 12,
				vx: rand(-0.04, 0.04) * W, vy: -rand(1.0, 1.25) * H,
				targetY: rand(0.08, 0.34) * H, color: pick(colors)
			});
			st.timer = rand(0.35, 1.05);
		}
		ctx.save();
		ctx.globalCompositeOperation = 'lighter';
		var grav = 0.8 * H, apex = -0.05 * H;
		var i, r, s;
		for (i = st.rockets.length - 1; i >= 0; i--) {
			r = st.rockets[i];
			r.vy += grav * dt; r.x += r.vx * dt; r.y += r.vy * dt;
			ctx.globalAlpha = 1; ctx.fillStyle = r.color;
			ctx.shadowColor = r.color; ctx.shadowBlur = 10;
			ctx.beginPath(); ctx.arc(r.x, r.y, 2.2, 0, 6.283); ctx.fill();
			if (r.vy > apex || r.y <= r.targetY) { explode(st, r.x, r.y, r.color, colors, H); st.rockets.splice(i, 1); }
		}
		ctx.shadowBlur = 0;
		for (i = st.sparks.length - 1; i >= 0; i--) {
			s = st.sparks[i];
			s.age += dt;
			var drag = 1 - 1.4 * dt;
			s.vx *= drag; s.vy = s.vy * drag + 0.12 * H * dt;
			s.x += s.vx * dt; s.y += s.vy * dt;
			var a = 1 - s.age / s.life;
			if (a <= 0) { st.sparks.splice(i, 1); continue; }
			ctx.globalAlpha = a; ctx.fillStyle = s.color;
			ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, 6.283); ctx.fill();
		}
		ctx.restore();
	}

	function explode(st, x, y, color, colors, H) {
		var n = Math.round(rand(38, 62));
		var mono = Math.random() < 0.55;
		for (var i = 0; i < n; i++) {
			var a = (i / n) * 6.283 + rand(-0.06, 0.06);
			var sp = rand(0.07, 0.22) * H;
			st.sparks.push({
				x: x, y: y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
				life: rand(0.9, 1.7), age: 0, r: rand(1.4, 2.6),
				color: mono ? color : pick(colors)
			});
		}
	}

	/* ------------------------------------------------------------------ *
	 * Decorative SVG overlays
	 * ------------------------------------------------------------------ */
	function layoutBulbs(top) {
		top.querySelectorAll('.hx-bulb').forEach(function (b) { b.remove(); });
		var bulbColors = ['#ff3b3b', '#ffd23f', '#4cc38a', '#4aa3ff', '#ff7bd5'];
		var gap = 34, n = Math.ceil(window.innerWidth / gap) + 1;
		for (var i = 0; i < n; i++) {
			var b = document.createElement('span');
			b.className = 'hx-bulb';
			b.style.left = (i * gap) + 'px';
			b.style.background = bulbColors[i % bulbColors.length];
			b.style.color = bulbColors[i % bulbColors.length]; // drives the glow (currentColor)
			b.style.animationDelay = (Math.random() * -2).toFixed(2) + 's';
			b.style.top = (6 + (i % 2) * 6) + 'px';
			top.appendChild(b);
		}
	}

	/* ------------------------------------------------------------------ *
	 * Resolution + public API
	 * ------------------------------------------------------------------ */
	function resolve(today) {
		var params = new URLSearchParams(location.search);
		var ov = params.get('theme') || params.get('holiday');
		try {
			if (ov) {
				if (ov === 'auto') localStorage.removeItem(KEY);
				else localStorage.setItem(KEY, ov);
			}
			var stored = localStorage.getItem(KEY);
			if (stored) {
				if (stored === 'off' || stored === 'none') return null;
				if (stored !== 'auto') return byId(stored);
			}
		} catch (e) { /* storage blocked - fall through to auto */ }
		return pickAuto(today);
	}

	apply(resolve(midnight(new Date())));
})();
