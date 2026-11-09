document.addEventListener('DOMContentLoaded', () => {
  // Network background animation
  const canvas = document.getElementById('network-bg');
  const ctx = canvas.getContext('2d');
  let width, height;
  let particles = [];
  const particleCount = 60;
  const connectionDistance = 120;
  let mouse = { x: null, y: null };

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }

  function initParticles() {
    particles = [];
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        radius: Math.random() * 2 + 1
      });
    }
  }

  function animate() {
    ctx.clearRect(0, 0, width, height);
    
    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      
      if (p.x < 0 || p.x > width) p.vx *= -1;
      if (p.y < 0 || p.y > height) p.vy *= -1;
      
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(56, 189, 248, 0.6)';
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
          ctx.strokeStyle = `rgba(56, 189, 248, ${0.2 * (1 - dist / connectionDistance)})`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    }
    
    requestAnimationFrame(animate);
  }

  resize();
  initParticles();
  animate();
  
  window.addEventListener('resize', () => {
    resize();
    initParticles();
  });

  // Navigation scroll effect
  const nav = document.querySelector('nav');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
      nav.classList.add('scrolled');
    } else {
      nav.classList.remove('scrolled');
    }
  });

  // Reveal on scroll
  const reveals = document.querySelectorAll('.reveal');
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('active');
      }
    });
  }, { threshold: 0.1 });

  reveals.forEach(el => revealObserver.observe(el));

  // Tabs
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');
  
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.dataset.tab;
      
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanels.forEach(p => p.classList.remove('active'));
      
      btn.classList.add('active');
      document.getElementById(tabId).classList.add('active');
    });
  });

  // Animated counters
  const counters = document.querySelectorAll('.hero-stat-number');
  const counterObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const target = parseInt(entry.target.dataset.target);
        animateCounter(entry.target, target);
        counterObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });

  counters.forEach(counter => counterObserver.observe(counter));

  function animateCounter(element, target) {
    let current = 0;
    const increment = target / 60;
    const timer = setInterval(() => {
      current += increment;
      if (current >= target) {
        element.textContent = target;
        clearInterval(timer);
      } else {
        element.textContent = Math.floor(current);
      }
    }, 25);
  }

  // Smooth scroll for nav links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  // SVG bar chart hover effects
  const bars = document.querySelectorAll('.bar');
  bars.forEach(bar => {
    bar.addEventListener('mouseenter', () => {
      const value = bar.getAttribute('data-value');
      const label = bar.getAttribute('data-label');
      showTooltip(bar, `${label}: ${value}%`);
    });
    bar.addEventListener('mouseleave', hideTooltip);
  });

  function showTooltip(element, text) {
    let tooltip = document.querySelector('.chart-tooltip');
    if (!tooltip) {
      tooltip = document.createElement('div');
      tooltip.className = 'chart-tooltip';
      tooltip.style.cssText = `
        position: absolute;
        background: rgba(17, 24, 39, 0.95);
        border: 1px solid var(--accent);
        color: var(--text-primary);
        padding: 0.5rem 1rem;
        border-radius: 8px;
        font-size: 0.85rem;
        pointer-events: none;
        z-index: 1000;
        transition: opacity 0.2s ease;
      `;
      document.body.appendChild(tooltip);
    }
    tooltip.textContent = text;
    tooltip.style.opacity = '1';
    
    const rect = element.getBoundingClientRect();
    tooltip.style.left = `${rect.left + rect.width / 2 - tooltip.offsetWidth / 2}px`;
    tooltip.style.top = `${rect.top - tooltip.offsetHeight - 10 + window.scrollY}px`;
  }

  function hideTooltip() {
    const tooltip = document.querySelector('.chart-tooltip');
    if (tooltip) {
      tooltip.style.opacity = '0';
    }
  }
});
