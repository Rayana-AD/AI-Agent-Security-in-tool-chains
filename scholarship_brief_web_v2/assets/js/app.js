document.addEventListener('DOMContentLoaded', () => {
  initNetworkBg();
  initNav();
  initReveal();
  initTabs();
  initCounters();
  initSmoothScroll();
  initScopeAccordion();
  initCharts();
});

function initNetworkBg() {
  const canvas = document.getElementById('network-bg');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let width, height, particles = [];
  const particleCount = 70, connectionDistance = 130;

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  function initParticles() {
    particles = [];
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * width, y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.4,
        radius: Math.random() * 2 + 1
      });
    }
  }
  function animate() {
    ctx.clearRect(0, 0, width, height);
    particles.forEach(p => {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > width) p.vx *= -1;
      if (p.y < 0 || p.y > height) p.vy *= -1;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(56, 189, 248, 0.55)';
      ctx.fill();
    });
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < connectionDistance) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(56, 189, 248, ${0.18 * (1 - dist / connectionDistance)})`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(animate);
  }
  resize(); initParticles(); animate();
  window.addEventListener('resize', () => { resize(); initParticles(); });
}

function initNav() {
  const nav = document.querySelector('nav');
  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 50);
  });
}

function initReveal() {
  const reveals = document.querySelectorAll('.reveal');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('active'); });
  }, { threshold: 0.08, rootMargin: '0px 0px -50px 0px' });
  reveals.forEach(el => observer.observe(el));
}

function initTabs() {
  document.querySelectorAll('.tabs').forEach(tabGroup => {
    const btns = tabGroup.querySelectorAll('.tab-btn');
    const panels = tabGroup.parentElement.querySelectorAll('.tab-panel');
    btns.forEach(btn => {
      btn.addEventListener('click', () => {
        const tabId = btn.dataset.tab;
        btns.forEach(b => b.classList.remove('active'));
        panels.forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(tabId).classList.add('active');
      });
    });
  });
}

function initCounters() {
  const counters = document.querySelectorAll('.hero-stat-number');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const target = parseInt(entry.target.dataset.target);
        animateCounter(entry.target, target);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });
  counters.forEach(c => observer.observe(c));
}

function animateCounter(element, target) {
  let current = 0;
  const increment = target / 50;
  const timer = setInterval(() => {
    current += increment;
    if (current >= target) { element.textContent = target; clearInterval(timer); }
    else element.textContent = Math.floor(current);
  }, 28);
}

function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

function initScopeAccordion() {
  const cards = document.querySelectorAll('.scope-card');
  cards.forEach(card => {
    const header = card.querySelector('.scope-header');
    header.addEventListener('click', () => {
      const wasActive = card.classList.contains('active');
      cards.forEach(c => c.classList.remove('active'));
      if (!wasActive) card.classList.add('active');
    });
  });
  if (cards.length > 0) cards[0].classList.add('active');
}

function initCharts() {
  if (typeof Chart === 'undefined') return;
  Chart.defaults.color = '#94a3b8';
  Chart.defaults.font.family = 'Inter, sans-serif';
  Chart.defaults.font.size = 12;

  const securityCtx = document.getElementById('securityChart');
  if (securityCtx) {
    new Chart(securityCtx, {
      type: 'bar',
      data: {
        labels: ['Banking', 'Slack', 'Workspace', 'Travel'],
        datasets: [
          { label: 'Spotlighting', data: [62, 48, 35, 40], backgroundColor: 'rgba(245, 158, 11, 0.75)', borderColor: '#f59e0b', borderWidth: 1, borderRadius: 6 },
          { label: 'PI Detector', data: [82, 75, 55, 60], backgroundColor: 'rgba(96, 165, 250, 0.75)', borderColor: '#60a5fa', borderWidth: 1, borderRadius: 6 },
          { label: 'AI Safety Harness', data: [99, 98, 94, 96], backgroundColor: 'rgba(52, 211, 153, 0.85)', borderColor: '#34d399', borderWidth: 1, borderRadius: 6 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { color: '#f8fafc', usePointStyle: true, padding: 20 } },
          tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.95)', borderColor: 'rgba(56, 189, 248, 0.3)', borderWidth: 1,
            titleColor: '#f8fafc', bodyColor: '#94a3b8', padding: 12,
            callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}% (relative efficacy)` }
          }
        },
        scales: {
          y: { beginAtZero: true, max: 100, grid: { color: 'rgba(51, 65, 85, 0.5)' }, ticks: { callback: v => v + '%' }, title: { display: true, text: 'Relative Defense Efficacy', color: '#64748b' } },
          x: { grid: { display: false } }
        }
      }
    });
  }

  const tradeCtx = document.getElementById('tradeoffChart');
  if (tradeCtx) {
    new Chart(tradeCtx, {
      type: 'scatter',
      data: {
        datasets: [{
          label: 'Defense Layers',
          data: [
            { x: 68, y: 35, r: 12, label: 'No Defense' },
            { x: 72, y: 52, r: 12, label: 'Spotlighting' },
            { x: 45, y: 76, r: 12, label: 'PI Detector' },
            { x: 81, y: 98, r: 16, label: 'AI Safety Harness' }
          ],
          backgroundColor: ['rgba(248, 113, 113, 0.85)', 'rgba(245, 158, 11, 0.85)', 'rgba(96, 165, 250, 0.85)', 'rgba(52, 211, 153, 0.9)'],
          borderColor: ['#f87171', '#f59e0b', '#60a5fa', '#34d399'], borderWidth: 2
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.95)', borderColor: 'rgba(56, 189, 248, 0.3)', borderWidth: 1,
            titleColor: '#f8fafc', bodyColor: '#94a3b8', padding: 12,
            callbacks: {
              title: ctx => ctx[0].raw.label,
              label: ctx => [`Utility: ${ctx.parsed.x}%`, `Security: ${ctx.parsed.y}%`, 'Qualitative trend']
            }
          }
        },
        scales: {
          x: { min: 30, max: 100, grid: { color: 'rgba(51, 65, 85, 0.5)' }, title: { display: true, text: 'Utility Retention (%)', color: '#64748b' } },
          y: { min: 20, max: 100, grid: { color: 'rgba(51, 65, 85, 0.5)' }, title: { display: true, text: 'Security Efficacy (%)', color: '#64748b' } }
        }
      }
    });
  }

  const radarCtx = document.getElementById('radarChart');
  if (radarCtx) {
    new Chart(radarCtx, {
      type: 'radar',
      data: {
        labels: ['IPI', 'Jailbreak', 'CoT Hijack', 'Multi-Agent', 'Multi-Modal', 'Backdoor'],
        datasets: [
          { label: 'Current Coverage', data: [95, 40, 30, 25, 20, 15], backgroundColor: 'rgba(56, 189, 248, 0.2)', borderColor: '#38bdf8', borderWidth: 2, pointBackgroundColor: '#38bdf8' },
          { label: 'Target Coverage', data: [98, 85, 80, 75, 70, 65], backgroundColor: 'rgba(52, 211, 153, 0.15)', borderColor: '#34d399', borderWidth: 2, borderDash: [6, 4], pointBackgroundColor: '#34d399' }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { color: '#f8fafc', usePointStyle: true } },
          tooltip: { backgroundColor: 'rgba(15, 23, 42, 0.95)', borderColor: 'rgba(56, 189, 248, 0.3)', borderWidth: 1, titleColor: '#f8fafc', bodyColor: '#94a3b8' }
        },
        scales: {
          r: { beginAtZero: true, max: 100, grid: { color: 'rgba(51, 65, 85, 0.5)' }, pointLabels: { color: '#94a3b8', font: { size: 11 } }, ticks: { backdropColor: 'transparent', color: '#64748b' } }
        }
      }
    });
  }
}
