'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import Script from 'next/script';

const faqData = [
  {
    q: 'How does Callwen handle sensitive client data?',
    a: 'All data is encrypted in transit (TLS 1.2+) and at rest (AES-256). Your documents are stored on SOC 2 Type II certified infrastructure in US-based data centers. We never use your data to train AI models. Our AI providers (OpenAI and Anthropic) process queries via their commercial APIs with zero data retention.',
  },
  {
    q: 'What is IRC \u00a77216 and why does it matter?',
    a: 'IRC Section 7216 requires written client consent before a tax preparer can disclose or use tax return information for purposes beyond the original engagement. Callwen has built-in consent tracking with e-signature capture, expiration alerts, and audit trails, so you stay compliant without spreadsheets.',
  },
  {
    q: 'What types of documents can I upload?',
    a: 'Tax returns (1040, 1120, 1065, 1120-S), W-2s, K-1s, engagement letters, meeting recordings (audio/video), email threads, financial statements, and any PDF, Word, Excel, or text file. Callwen auto-classifies tax documents and extracts text from all formats.',
  },
  {
    q: 'How accurate are the AI answers?',
    a: 'Every AI response includes a confidence score and source citations pointing to the specific document and page. You can verify any answer by clicking the source reference. We route between fast lookups for standard queries and deep analysis for complex questions to balance speed and accuracy.',
  },
  {
    q: 'Can my team share a workspace?',
    a: 'Yes. The Firm plan includes 3 seats with additional seats at $79/month each. Team members share a unified client knowledge base with role-based access controls. Admins can assign specific clients to specific team members.',
  },
  {
    q: 'How long does setup take?',
    a: 'Under two minutes. Sign up, upload your first documents, and start asking questions. There is no onboarding call required, no data migration, and no IT department needed. Connect Gmail or Outlook in one click to auto-sync client emails.',
  },
  {
    q: 'Can I cancel anytime?',
    a: 'Yes. No contracts, no cancellation fees. Cancel from your account settings and your subscription ends at the end of the current billing period. You can export all your data at any time.',
  },
];

export default function LandingPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const threeLoaded = useRef(false);

  // State for interactive elements
  const [menuOpen, setMenuOpen] = useState(false);
  const [annualBilling, setAnnualBilling] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [showCookieBanner, setShowCookieBanner] = useState(false);
  const [currentSlide, setCurrentSlide] = useState(0);
  const carouselPaused = useRef(false);

  // Initialize Three.js scene after script loads
  const initThree = () => {
    // Skip Three.js on mobile for performance
    if (window.innerWidth < 768) return;
    if (threeLoaded.current || !canvasRef.current || typeof window === 'undefined') return;
    const THREE = (window as any).THREE;
    if (!THREE) return;
    threeLoaded.current = true;

    const canvas = canvasRef.current;
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.4;

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x0c0e13, 0.014);
    const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 120);
    camera.position.z = 22;

    // Lighting
    scene.add(new THREE.AmbientLight(0xffffff, 0.3));
    const key = new THREE.DirectionalLight(0xc9944a, 1.0);
    key.position.set(8, 12, 15);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x5bb8af, 0.4);
    fill.position.set(-8, -5, -10);
    scene.add(fill);
    const rim = new THREE.DirectionalLight(0xe8b06a, 0.6);
    rim.position.set(0, 15, -5);
    scene.add(rim);
    const glow1 = new THREE.PointLight(0xc9944a, 2.5, 30);
    glow1.position.set(6, 5, 8);
    scene.add(glow1);
    const glow2 = new THREE.PointLight(0x5bb8af, 1.2, 25);
    glow2.position.set(-8, -3, 5);
    scene.add(glow2);
    const glow3 = new THREE.PointLight(0xe8b06a, 1.5, 20);
    glow3.position.set(0, -8, 10);
    scene.add(glow3);

    // Doc texture generator
    function makeDocTex(v: number) {
      const c = document.createElement('canvas');
      c.width = 128; c.height = 180;
      const x = c.getContext('2d')!;
      const bgs = ['#2a2f3e','#303648','#353c4e','#282d3a'];
      x.fillStyle = bgs[v % bgs.length];
      x.fillRect(0,0,128,180);
      x.fillStyle = 'rgba(255,255,255,0.015)';
      for(let i=0;i<200;i++) x.fillRect(Math.random()*128, Math.random()*180, 1, 1);
      x.fillStyle = v%3===0 ? 'rgba(201,148,74,0.6)' : v%3===1 ? 'rgba(91,184,175,0.45)' : 'rgba(232,176,106,0.4)';
      x.fillRect(12, 14, 40+Math.random()*35, 5);
      x.fillStyle = 'rgba(240,237,230,0.2)';
      x.fillRect(12, 26, 60+Math.random()*40, 3);
      x.fillStyle = 'rgba(201,148,74,0.12)';
      x.fillRect(12, 36, 104, 0.5);
      x.fillStyle = 'rgba(240,237,230,0.13)';
      let ly = 44;
      const lc = 7 + Math.floor(Math.random()*5);
      for(let i=0;i<lc;i++) x.fillRect(12, ly+i*11, 25+Math.random()*78, 2.5);
      if(v%4===0){
        x.strokeStyle='rgba(201,148,74,0.2)';x.lineWidth=0.8;
        x.strokeRect(12,105,104,50);
        x.beginPath();x.moveTo(12,122);x.lineTo(116,122);x.moveTo(12,138);x.lineTo(116,138);
        x.moveTo(55,105);x.lineTo(55,155);x.moveTo(85,105);x.lineTo(85,155);x.stroke();
        x.fillStyle='rgba(240,237,230,0.1)';
        x.fillRect(16,110,25,3);x.fillRect(58,110,20,3);x.fillRect(88,110,18,3);
        x.fillRect(16,126,30,3);x.fillRect(58,126,15,3);x.fillRect(88,126,22,3);
      }
      if(v%3===1){
        x.fillStyle='rgba(201,148,74,0.12)';
        x.beginPath();x.moveTo(128,0);x.lineTo(105,0);x.lineTo(128,23);x.closePath();x.fill();
        x.strokeStyle='rgba(201,148,74,0.15)';x.lineWidth=0.5;
        x.beginPath();x.moveTo(105,0);x.lineTo(128,23);x.stroke();
      }
      if(v%6===0){
        x.strokeStyle='rgba(91,184,175,0.25)';x.lineWidth=1;
        x.beginPath();x.arc(98,160,12,0,Math.PI*2);x.stroke();
        x.fillStyle='rgba(91,184,175,0.1)';
        x.beginPath();x.arc(98,160,12,0,Math.PI*2);x.fill();
      }
      const tex = new THREE.CanvasTexture(c);
      tex.minFilter = THREE.LinearFilter;
      return tex;
    }

    // Create 3D documents
    const DOC_COUNT = 70;
    const docs: any[] = [];
    const meshes: any[] = [];

    for(let i=0; i<DOC_COUNT; i++){
      const t = i/DOC_COUNT;
      const isClose = i < 10;
      const isMid = i < 30;
      const scale = isClose ? 1.2+Math.random()*0.7 : isMid ? 0.5+Math.random()*0.5 : 0.25+Math.random()*0.35;
      const w = scale;
      const h = scale * (1.3 + Math.random()*0.25);
      const d = 0.02 + scale*0.015;
      const geo = new THREE.BoxGeometry(w, h, d);
      const tex = makeDocTex(i);
      const faceOp = isClose ? 0.92 : isMid ? 0.7 : 0.45;
      const faceMat = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.65, metalness: 0.08, transparent: true, opacity: faceOp });
      const isAccent = i%4===0;
      const isTeal = i%7===0;
      const edgeCol = isAccent ? 0xc9944a : isTeal ? 0x5bb8af : 0x353c4e;
      const emInt = isAccent ? 0.6 : isTeal ? 0.4 : 0.05;
      const sideMat = new THREE.MeshStandardMaterial({ color: edgeCol, roughness: 0.4, metalness: 0.2, transparent: true, opacity: isClose ? 0.95 : 0.6, emissive: edgeCol, emissiveIntensity: emInt });
      const mesh = new THREE.Mesh(geo, [sideMat,sideMat,sideMat,sideMat,faceMat,faceMat]);
      const spiralAngle = t * Math.PI * 7 + (Math.random()-0.5)*1.2;
      const spiralR = isClose ? 11+Math.random()*5 : isMid ? 13+Math.random()*7 : 16+Math.random()*12;
      const ySpread = (Math.random()-0.5) * 55;
      mesh.position.x = Math.cos(spiralAngle) * spiralR;
      mesh.position.y = ySpread;
      mesh.position.z = Math.sin(spiralAngle) * spiralR * 0.35 - 2;
      mesh.rotation.x = (Math.random()-0.5)*0.6;
      mesh.rotation.y = (Math.random()-0.5)*0.9;
      mesh.rotation.z = (Math.random()-0.5)*0.4;
      if(isAccent || isTeal || isClose){
        const eg = new THREE.EdgesGeometry(geo);
        const eCol = isAccent ? 0xc9944a : isTeal ? 0x5bb8af : 0xe8b06a;
        const eOp = isClose ? 0.8 : 0.35;
        const em = new THREE.LineBasicMaterial({color:eCol, transparent:true, opacity:eOp});
        const el = new THREE.LineSegments(eg, em);
        mesh.add(el);
        mesh.userData.edgeLine = el;
        mesh.userData.edgeBaseOp = eOp;
      }
      scene.add(mesh);
      meshes.push(mesh);
      docs.push({ mesh, baseY: mesh.position.y, spiralAngle, spiralR, orbitSpeed: 0.025+Math.random()*0.035, driftOff: Math.random()*Math.PI*2, driftSpd: 0.12+Math.random()*0.2, rotSpdX: (Math.random()-0.5)*0.003, rotSpdZ: (Math.random()-0.5)*0.002, mouseInf: isClose?0.4:isMid?0.2:0.08, isClose, isMid, baseRotX: mesh.rotation.x, baseRotY: mesh.rotation.y });
    }

    // Connecting lines
    const MAX_CONN = 80;
    const CONN_DIST = 5.5;
    const lGeo = new THREE.BufferGeometry();
    const lPos = new Float32Array(MAX_CONN * 6);
    lGeo.setAttribute('position', new THREE.BufferAttribute(lPos, 3));
    lGeo.setDrawRange(0,0);
    const lMat = new THREE.LineBasicMaterial({color:0xc9944a, transparent:true, opacity:0.06});
    const connLines = new THREE.LineSegments(lGeo, lMat);
    scene.add(connLines);
    const lGeo2 = new THREE.BufferGeometry();
    const lPos2 = new Float32Array(MAX_CONN * 6);
    lGeo2.setAttribute('position', new THREE.BufferAttribute(lPos2, 3));
    lGeo2.setDrawRange(0,0);
    const lMat2 = new THREE.LineBasicMaterial({color:0x5bb8af, transparent:true, opacity:0.04});
    const connLines2 = new THREE.LineSegments(lGeo2, lMat2);
    scene.add(connLines2);

    // Particles
    const PC = 150;
    const pGeo = new THREE.BufferGeometry();
    const pArr = new Float32Array(PC*3);
    for(let i=0;i<PC;i++){ pArr[i*3]=(Math.random()-0.5)*45; pArr[i*3+1]=(Math.random()-0.5)*65; pArr[i*3+2]=(Math.random()-0.5)*25; }
    pGeo.setAttribute('position', new THREE.BufferAttribute(pArr, 3));
    const pMat = new THREE.PointsMaterial({color:0xe8b06a, size:0.07, transparent:true, opacity:0.55, sizeAttenuation:true});
    const particles = new THREE.Points(pGeo, pMat);
    scene.add(particles);

    // State
    let scrollY=0, tScrollY=0, prevScroll=0, scrollVel=0;
    let mX=0, mY=0, tMX=0, tMY=0;
    const onScroll = () => { tScrollY = window.pageYOffset; };
    const onMouse = (e: MouseEvent) => { tMX=(e.clientX/window.innerWidth-0.5)*2; tMY=(e.clientY/window.innerHeight-0.5)*2; };
    const onResize = () => { camera.aspect=window.innerWidth/window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth,window.innerHeight); };
    window.addEventListener('scroll', onScroll, {passive:true});
    window.addEventListener('mousemove', onMouse, {passive:true});
    window.addEventListener('resize', onResize);

    const clock = new THREE.Clock();
    let animId: number;
    const projVec = new THREE.Vector3();

    function animate(){
      animId = requestAnimationFrame(animate);
      const t = clock.getElapsedTime();
      scrollY += (tScrollY-scrollY)*0.06;
      mX += (tMX-mX)*0.05;
      mY += (tMY-mY)*0.05;
      scrollVel = Math.abs(scrollY-prevScroll);
      prevScroll = scrollY;
      const sN = scrollY*0.0008;
      const sMult = 1 + Math.min(scrollVel*0.2, 5);

      camera.position.x = mX*0.7;
      camera.position.y = -mY*0.4 - sN*3;
      camera.lookAt(mX*0.2, -sN*3, 0);

      glow1.position.x = 6+Math.sin(t*0.3)*4;
      glow1.position.y = 5+Math.cos(t*0.2)*3;
      glow1.intensity = 2.5 + Math.sin(t*0.5)*0.5;
      glow2.position.x = -8+Math.sin(t*0.25+2)*4;
      glow3.position.y = -8+Math.sin(t*0.35)*3;

      const CLEAR_X = 0.72, CLEAR_Y = 0.65, REPEL_STRENGTH = 8.0, FADE_ZONE = 0.2;

      for(let i=0; i<docs.length; i++){
        const dd = docs[i];
        const m = dd.mesh;
        const angle = dd.spiralAngle + t * dd.orbitSpeed * sMult * 0.25;
        m.position.x = Math.cos(angle)*dd.spiralR + Math.sin(t*dd.driftSpd+dd.driftOff)*0.4;
        m.position.z = Math.sin(angle)*dd.spiralR*0.35 - 2;
        m.position.y = dd.baseY - sN*(5+dd.spiralR*0.3) + Math.sin(t*dd.driftSpd*0.7+dd.driftOff)*0.5;
        m.position.x += mX * dd.mouseInf * 0.8;
        m.position.y += -mY * dd.mouseInf * 0.3;

        projVec.copy(m.position);
        projVec.project(camera);
        const ndcX = projVec.x;
        const ndcY = projVec.y;
        const normDist = Math.sqrt((ndcX*ndcX)/(CLEAR_X*CLEAR_X) + (ndcY*ndcY)/(CLEAR_Y*CLEAR_Y));
        let fadeFactor = 1.0;

        if(normDist < 1.0 + FADE_ZONE) {
          if(normDist < 1.0) {
            const force = (1.0 - normDist) * REPEL_STRENGTH;
            const pushDirX = ndcX >= 0 ? 1 : -1;
            const pushDirY = ndcY >= 0 ? 1 : -1;
            m.position.x += pushDirX * force * 1.8;
            m.position.y += pushDirY * force * 0.8;
            m.position.z -= force * 1.5;
          }
          fadeFactor = normDist < 1.0 ? normDist * normDist * 0.3 : Math.min(1.0, (normDist - 1.0) / FADE_ZONE * 0.6 + 0.4);
          const baseFaceOp = dd.isClose ? 0.92 : dd.isMid ? 0.7 : 0.45;
          const baseSideOp = dd.isClose ? 0.95 : 0.6;
          m.material[4].opacity = baseFaceOp * fadeFactor;
          m.material[5].opacity = baseFaceOp * fadeFactor;
          for(let s=0;s<4;s++) m.material[s].opacity = baseSideOp * fadeFactor;
        } else {
          const baseFaceOp = dd.isClose ? 0.92 : dd.isMid ? 0.7 : 0.45;
          const baseSideOp = dd.isClose ? 0.95 : 0.6;
          m.material[4].opacity = baseFaceOp;
          m.material[5].opacity = baseFaceOp;
          for(let s=0;s<4;s++) m.material[s].opacity = baseSideOp;
        }

        m.rotation.x += dd.rotSpdX * sMult;
        m.rotation.z += dd.rotSpdZ * sMult;
        const tiltStr = dd.isClose ? 0.2 : dd.isMid ? 0.1 : 0.04;
        m.rotation.x += (-mY*tiltStr - m.rotation.x)*0.025;
        m.rotation.y += (mX*tiltStr - m.rotation.y)*0.025;

        if(m.userData.edgeLine){
          const pulse = dd.isClose ? 0.15 : 0.08;
          const edgeFade = (normDist < 1.0 + FADE_ZONE) ? fadeFactor : 1.0;
          m.userData.edgeLine.material.opacity = (m.userData.edgeBaseOp + Math.sin(t*1.5+i)*pulse) * edgeFade;
        }
      }

      // Connections
      let li1=0, li2=0;
      const p1=connLines.geometry.attributes.position.array;
      const p2=connLines2.geometry.attributes.position.array;
      for(let i=0; i<meshes.length; i++){
        for(let j=i+1; j<meshes.length; j++){
          if(li1>=MAX_CONN && li2>=MAX_CONN) break;
          const a=meshes[i].position, b=meshes[j].position;
          const dx=a.x-b.x, dy=a.y-b.y, dz=a.z-b.z;
          const dist=Math.sqrt(dx*dx+dy*dy+dz*dz);
          if(dist<CONN_DIST){
            if(li1<MAX_CONN && (i+j)%2===0){
              const idx=li1*6;
              p1[idx]=a.x;p1[idx+1]=a.y;p1[idx+2]=a.z;
              p1[idx+3]=b.x;p1[idx+4]=b.y;p1[idx+5]=b.z;
              li1++;
            } else if(li2<MAX_CONN){
              const idx=li2*6;
              p2[idx]=a.x;p2[idx+1]=a.y;p2[idx+2]=a.z;
              p2[idx+3]=b.x;p2[idx+4]=b.y;p2[idx+5]=b.z;
              li2++;
            }
          }
        }
      }
      connLines.geometry.setDrawRange(0,li1*2);
      connLines.geometry.attributes.position.needsUpdate=true;
      lMat.opacity = 0.05+Math.sin(t*0.7)*0.025;
      connLines2.geometry.setDrawRange(0,li2*2);
      connLines2.geometry.attributes.position.needsUpdate=true;
      lMat2.opacity = 0.03+Math.sin(t*0.9+1)*0.02;

      // Particles
      const pp = particles.geometry.attributes.position.array;
      for(let i=0;i<PC;i++){
        pp[i*3+1] -= 0.006*sMult;
        if(pp[i*3+1]<-32) pp[i*3+1]=32;
        pp[i*3] += Math.sin(t*0.4+i*0.3)*0.002;
      }
      particles.geometry.attributes.position.needsUpdate=true;
      particles.position.y = -sN*4;

      renderer.render(scene, camera);
    }

    animate();

    // Return cleanup
    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('mousemove', onMouse);
      window.removeEventListener('resize', onResize);
      renderer.dispose();
    };
  };

  // Setup scroll nav, reveal animations
  useEffect(() => {
    // Nav scroll
    const nav = navRef.current;
    const handleScroll = () => {
      nav?.classList.toggle('scrolled', window.scrollY > 50);
    };
    window.addEventListener('scroll', handleScroll);

    // Reveal animations
    const obs = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add('visible');
          obs.unobserve(e.target);
        }
      });
    }, { threshold: 0.15 });
    document.querySelectorAll('[data-reveal]').forEach((el) => obs.observe(el));

    // Smooth scroll for hash links
    const handleHashClick = (e: Event) => {
      const anchor = (e.currentTarget as HTMLAnchorElement);
      const href = anchor.getAttribute('href');
      if (href?.startsWith('#')) {
        e.preventDefault();
        const target = document.querySelector(href);
        target?.scrollIntoView({ behavior: 'smooth' });
      }
    };
    const hashLinks = document.querySelectorAll('a[href^="#"]');
    hashLinks.forEach((a) => a.addEventListener('click', handleHashClick));

    return () => {
      window.removeEventListener('scroll', handleScroll);
      obs.disconnect();
      hashLinks.forEach((a) => a.removeEventListener('click', handleHashClick));
    };
  }, []);

  // Close mobile menu when clicking outside
  useEffect(() => {
    if (!menuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('.nav')) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [menuOpen]);

  // Cookie consent banner — delayed show, persisted via document.cookie
  useEffect(() => {
    if (document.cookie.split(';').some(c => c.trim().startsWith('callwen_consent='))) return;
    const timer = setTimeout(() => setShowCookieBanner(true), 1500);
    return () => clearTimeout(timer);
  }, []);

  // Testimonial carousel auto-advance
  const TESTIMONIAL_COUNT = 6;
  const SLIDES_VISIBLE = typeof window !== 'undefined' && window.innerWidth < 768 ? 1 : 3;
  const MAX_SLIDE = TESTIMONIAL_COUNT - SLIDES_VISIBLE;
  useEffect(() => {
    const interval = setInterval(() => {
      if (!carouselPaused.current) {
        setCurrentSlide(prev => (prev >= MAX_SLIDE ? 0 : prev + 1));
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [MAX_SLIDE]);

  const handleCookieConsent = (accepted: boolean) => {
    const value = accepted ? 'true' : 'declined';
    document.cookie = `callwen_consent=${value};path=/;max-age=${60 * 60 * 24 * 365};SameSite=Lax`;
    setShowCookieBanner(false);
  };

  // Three.js cleanup ref
  const cleanupRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    return () => { cleanupRef.current?.(); };
  }, []);

  // Pricing helpers
  const starterPrice = annualBilling ? 79 : 99;
  const proPrice = annualBilling ? 119 : 149;

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: landingCSS }} />

      <Script
        src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
        strategy="afterInteractive"
        onLoad={() => {
          const cleanup = initThree();
          if (cleanup) cleanupRef.current = cleanup;
        }}
      />

      <canvas ref={canvasRef} id="three-canvas" />

      <div className="page-content">
        {/* Nav */}
        <nav className="nav" ref={navRef}>
          <div className="nav-inner">
            <div className="nav-logo">Call<span>wen</span></div>
            <div className="nav-links">
              <a href="#features">Features</a>
              <a href="#pricing">Pricing</a>
              <a href="#extension">Extension</a>
              <Link href="/sign-in">Log in</Link>
              <Link href="/sign-in" className="nav-cta">Get started</Link>
            </div>
            <button
              className={`hamburger${menuOpen ? ' open' : ''}`}
              onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
              aria-label="Toggle menu"
            >
              <span /><span /><span />
            </button>
          </div>
          {menuOpen && (
            <div className="mobile-menu">
              <a href="#features" onClick={() => setMenuOpen(false)}>Features</a>
              <a href="#pricing" onClick={() => setMenuOpen(false)}>Pricing</a>
              <a href="#extension" onClick={() => setMenuOpen(false)}>Extension</a>
              <Link href="/sign-in" onClick={() => setMenuOpen(false)}>Log in</Link>
              <Link href="/sign-in" className="mobile-menu-cta" onClick={() => setMenuOpen(false)}>Get started</Link>
            </div>
          )}
        </nav>

        {/* Hero */}
        <section className="splash">
          <div className="hero-split">
            <div className="hero-left">
              <div className="hero-badge"><span className="pulse" /> AI-Powered Document Intelligence</div>
              <h1>Your documents,<br /><em>finally</em> answering<br />your questions.</h1>
              <p className="subtitle">Upload tax returns, meeting recordings, and client files. Ask anything. Get cited answers with confidence scores in seconds.</p>
              <div className="hero-buttons">
                <Link href="/sign-in" className="btn btn-primary">
                  Start free <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 8h10M9 4l4 4-4 4"/></svg>
                </Link>
                <a href="#features" className="btn btn-ghost">See how it works</a>
              </div>
            </div>
            <div className="hero-right">
              <div className="hero-player">
                <video
                  className="hero-video"
                  autoPlay
                  muted
                  loop
                  playsInline
                  preload="auto"
                  ref={(el) => {
                    if (el) el.dataset.ref = 'hero-video';
                  }}
                  onClick={(e) => {
                    const v = e.currentTarget;
                    if (v.muted) { v.muted = false; } else { v.muted = true; }
                  }}
                >
                  <source src="/hero-video.mp4" type="video/mp4" />
                </video>
                <button
                  className="hero-play-btn"
                  aria-label="Toggle sound"
                  onClick={(e) => {
                    const v = (e.currentTarget.parentElement as HTMLElement).querySelector('video');
                    if (v) { v.muted = !v.muted; }
                  }}
                >
                  <svg viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="23" stroke="currentColor" strokeWidth="1.5" opacity="0.6"/><path d="M19 16l12 8-12 8z" fill="currentColor"/></svg>
                </button>
              </div>
            </div>
          </div>
          <div className="rule" />
          <div className="scroll-hint">Explore</div>
        </section>

        {/* Trust badges */}
        <div className="trust-badges-section" data-reveal>
          <p className="trust-badges-label">Built on standards CPAs trust</p>
          <div className="trust-badges-row">
            <span className="trust-badge">
              <svg viewBox="0 0 38 38" fill="none" strokeLinecap="round" strokeLinejoin="round">
                <rect x="4" y="8" width="30" height="24" rx="3" stroke="#c9944a" strokeWidth="1.2" fill="none" />
                <line x1="4" y1="14" x2="34" y2="14" stroke="#c9944a" strokeWidth="0.8" fill="none" />
                <text x="19" y="12" textAnchor="middle" fontFamily="'Cormorant Garamond', Georgia, serif" fontSize="7" fontWeight="600" fill="#c9944a">AICPA</text>
                <path d="M14 22l3 3 7-7" stroke="#c9944a" strokeWidth="1.5" fill="none" />
              </svg>
              <span className="trust-badge-label">AICPA Standards Aligned</span>
            </span>
            <span className="trust-badge">
              <svg viewBox="0 0 38 38" fill="none" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 3L33 10V19C33 27.5 26.5 33.5 19 36C11.5 33.5 5 27.5 5 19V10L19 3Z" stroke="#c9944a" strokeWidth="1.2" fill="rgba(201,148,74,0.06)" />
                <text x="19" y="17" textAnchor="middle" fontFamily="'Outfit', sans-serif" fontSize="6" fontWeight="500" fill="#c9944a">SOC 2</text>
                <text x="19" y="24" textAnchor="middle" fontFamily="'Outfit', sans-serif" fontSize="5" fontWeight="400" fill="#8a8680">TYPE II</text>
              </svg>
              <span className="trust-badge-label">SOC 2 Compliant Infrastructure</span>
            </span>
            <span className="trust-badge">
              <svg viewBox="0 0 38 38" fill="none" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="5" width="20" height="28" rx="2" stroke="#c9944a" strokeWidth="1.2" fill="none" />
                <text x="19" y="10" textAnchor="middle" fontFamily="'Outfit', sans-serif" fontSize="4.5" fontWeight="500" fill="#c9944a">§7216</text>
                <line x1="14" y1="14" x2="24" y2="14" stroke="#c9944a" strokeWidth="0.8" opacity="0.5" fill="none" />
                <line x1="14" y1="18" x2="24" y2="18" stroke="#c9944a" strokeWidth="0.8" opacity="0.5" fill="none" />
                <line x1="14" y1="22" x2="21" y2="22" stroke="#c9944a" strokeWidth="0.8" opacity="0.5" fill="none" />
                <path d="M22 25l2.5 2.5 5-5" stroke="#c9944a" strokeWidth="1.3" fill="none" />
              </svg>
              <span className="trust-badge-label">IRC §7216 Consent Built-In</span>
            </span>
            <span className="trust-badge">
              <svg viewBox="0 0 38 38" fill="none" strokeLinecap="round" strokeLinejoin="round">
                <rect x="8" y="16" width="22" height="17" rx="3" stroke="#c9944a" strokeWidth="1.2" fill="rgba(201,148,74,0.06)" />
                <path d="M14 16V11C14 7.5 16.2 5 19 5C21.8 5 24 7.5 24 11V16" stroke="#c9944a" strokeWidth="1.2" fill="none" />
                <circle cx="19" cy="24" r="2.5" fill="#c9944a" fillOpacity="0.7" />
                <line x1="19" y1="26.5" x2="19" y2="29" stroke="#c9944a" strokeWidth="1.2" fill="none" />
              </svg>
              <span className="trust-badge-label">AES-256 Encryption</span>
            </span>
            <span className="trust-badge">
              <svg viewBox="0 0 38 38" fill="none" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="19" cy="19" r="14" stroke="#c9944a" strokeWidth="1.2" fill="none" />
                <ellipse cx="19" cy="19" rx="7" ry="14" stroke="#c9944a" strokeWidth="0.8" fill="none" />
                <line x1="5" y1="12" x2="33" y2="12" stroke="#c9944a" strokeWidth="0.6" opacity="0.4" fill="none" />
                <line x1="5" y1="19" x2="33" y2="19" stroke="#c9944a" strokeWidth="0.6" opacity="0.4" fill="none" />
                <line x1="5" y1="26" x2="33" y2="26" stroke="#c9944a" strokeWidth="0.6" opacity="0.4" fill="none" />
                <circle cx="15" cy="16" r="3.5" stroke="#c9944a" strokeWidth="1" fill="rgba(201,148,74,0.1)" />
                <text x="15" y="18" textAnchor="middle" fontFamily="'Outfit', sans-serif" fontSize="5" fontWeight="500" fill="#c9944a">US</text>
              </svg>
              <span className="trust-badge-label">US-Only Data Centers</span>
            </span>
            <span className="trust-badge">
              <svg viewBox="0 0 38 38" fill="none" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="19" cy="19" r="13" stroke="#c9944a" strokeWidth="1.2" fill="none" />
                <path d="M19 10V19L25 22" stroke="#c9944a" strokeWidth="1.2" fill="none" />
                <line x1="10" y1="10" x2="28" y2="28" stroke="#c9944a" strokeWidth="1.2" opacity="0.6" fill="none" />
                <text x="19" y="36" textAnchor="middle" fontFamily="'Outfit', sans-serif" fontSize="4" fontWeight="400" fill="#8a8680">0 retention</text>
              </svg>
              <span className="trust-badge-label">Zero AI Data Retention</span>
            </span>
          </div>
        </div>

        {/* Feature sections */}
        <div className="sections" id="features">
          <div className="section left" data-reveal>
            <div className="number">01</div>
            <div className="content">
              <h2>Every document,<br /><em>one place</em></h2>
              <p>Tax returns, engagement letters, meeting recordings, emails. Drop them in and they&apos;re indexed on the spot. Callwen reads PDFs, audio, video, and spreadsheets so you never have to dig through folders again.</p>
              <span className="tag">Upload · Index · Organize</span>
            </div>
            <div className="section-visual section-visual-img" aria-hidden="true">
              <img
                src="/images/feature-01-documents.png"
                alt="Callwen client management interface showing organized client list with document counts and engagement types"
                style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top left', borderRadius: '12px' }}
              />
            </div>
          </div>

          <div className="section right" data-reveal>
            <div className="number">02</div>
            <div className="content">
              <h2>Ask questions,<br />get <em>real answers</em></h2>
              <p>Not generic summaries. Callwen gives you real answers with citations, confidence scores, and page references. When you tell a client &quot;the answer is on page 4,&quot; you know it&apos;s on page 4.</p>
              <span className="tag">AI · Source citations · Confidence</span>
            </div>
            <div className="section-visual section-visual-img" aria-hidden="true">
              <img
                src="/images/feature-02-ai-chat.png"
                alt="AI-powered Q&A showing a tax compensation breakdown with source citations"
                style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top', borderRadius: '12px' }}
              />
            </div>
          </div>

          <div className="section left" data-reveal>
            <div className="number">03</div>
            <div className="content">
              <h2>7216 compliance,<br /><em>built in</em></h2>
              <p>Tax documents are auto-detected. Consent forms with mandatory IRS language are generated in one click. E-signatures, expiration tracking, and smart alerts.</p>
              <span className="tag">IRC {'\u00a7'}7216 · Auto-detection · E-sign</span>
            </div>
            <div className="section-visual section-visual-img section-visual-consent" aria-hidden="true">
              <img
                src="/images/feature-03-consent.png"
                alt="IRC §7216 consent tracking showing obtained status with expiration date"
                style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center', borderRadius: '12px' }}
              />
            </div>
          </div>

          <div className="section right" data-reveal>
            <div className="number">04</div>
            <div className="content">
              <h2>Your firm,<br /><em>one workspace</em></h2>
              <p>Assign team members to clients. Share documents without sharing logins. Role-based access means associates see what they need, and partners see everything.</p>
              <span className="tag">Teams · Client allocation · Roles</span>
            </div>
            <div className="section-visual" aria-hidden="true">
              <div className="vis-team">
                <div className="team-avatar">SV</div>
                <div className="team-avatar">JM</div>
                <div className="team-avatar">KL</div>
              </div>
            </div>
          </div>

          <div className="section left" data-reveal id="extension">
            <div className="number">05</div>
            <div className="content">
              <h2>Capture anything,<br /><em>from anywhere</em></h2>
              <p>The Callwen browser extension lives in your sidebar. Select text from an email, screenshot a chart, or right-click a PDF link. Two clicks and it&apos;s in your client&apos;s file. Auto-matching knows which client you&apos;re working on, and Quick Query lets you ask questions without leaving the page.</p>
              <span className="tag">Chrome Extension · Auto-match · Quick Query</span>
            </div>
            <div className="section-visual section-visual-img section-visual-ext" aria-hidden="true">
              <img
                src="/images/feature-05-extension.png"
                alt="Callwen browser extension showing document capture with client auto-matching"
                style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: '12px' }}
              />
            </div>
          </div>
        </div>

        {/* Cost Comparison Table */}
        <div className="cost-section" data-reveal>
          <div className="cost-inner">
            <p className="overline">The real cost of &ldquo;free&rdquo; tools</p>
            <h2>Replace your tool stack</h2>
            <p className="cost-subtitle">CPAs cobble together 4–6 separate tools. Callwen replaces them all.</p>

            <div className="cost-table-wrap">
              <table className="cost-table">
                <thead>
                  <tr>
                    <th className="cost-th tool-col">Tool</th>
                    <th className="cost-th price-col">Typical cost</th>
                    <th className="cost-th callwen-col">
                      <span className="callwen-badge">Callwen</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { tool: 'Document management (SharePoint / Google Drive)', cost: '$12/user/mo' },
                    { tool: 'AI search & chat (ChatGPT Team / Copilot)', cost: '$25/user/mo' },
                    { tool: 'E-signature & consent (DocuSign / PandaDoc)', cost: '$25/user/mo' },
                    { tool: 'Meeting transcription (Otter / Fireflies)', cost: '$17/user/mo' },
                    { tool: 'Email sync CRM (Front / HubSpot)', cost: '$29/user/mo' },
                    { tool: 'Tax research (Checkpoint / CCH)', cost: '$150+/mo' },
                  ].map((row, i) => (
                    <tr key={i} className="cost-row">
                      <td className="cost-td tool-col">{row.tool}</td>
                      <td className="cost-td price-col">{row.cost}</td>
                      <td className="cost-td callwen-col">
                        <svg className="cost-check" viewBox="0 0 20 20" fill="none">
                          <path d="M5 10l3.5 3.5L15 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="cost-total-row">
                    <td className="cost-td tool-col cost-total-label">Total without Callwen</td>
                    <td className="cost-td price-col cost-total-price">$258+<span className="cost-per">/user/mo</span></td>
                    <td className="cost-td callwen-col">
                      <span className="cost-callwen-price">From $99<span className="cost-per">/mo</span></span>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>

            <a href="#pricing" className="cost-cta">See pricing plans &rarr;</a>
          </div>
        </div>

        {/* Business Value / Impact Cards */}
        <div className="impact-section" data-reveal>
          <div className="impact-inner">
            <p className="overline">Built for how CPAs actually work</p>
            <h2>Measurable impact from day one</h2>
            <div className="impact-grid">
              <div className="impact-card">
                <div className="impact-number">5+</div>
                <div className="impact-unit">hours saved per week</div>
                <p className="impact-desc">Stop hunting through folders, inboxes, and portals. Ask a question, get a cited answer in seconds.</p>
              </div>
              <div className="impact-card">
                <div className="impact-number">100%</div>
                <div className="impact-unit">§7216 audit-ready</div>
                <p className="impact-desc">Every consent is tracked, timestamped, and exportable. No spreadsheets, no missed expirations.</p>
              </div>
              <div className="impact-card">
                <div className="impact-number">1-click</div>
                <div className="impact-unit">client briefing</div>
                <p className="impact-desc">Walk into every meeting with a full financial snapshot. Documents, emails, and action items all in one place.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Testimonial Carousel */}
        <div className="testimonials-section" data-reveal>
          <p className="overline">What CPAs are saying</p>
          <h2>Trusted by practitioners</h2>
          <div
            className="carousel-container"
            onMouseEnter={() => { carouselPaused.current = true; }}
            onMouseLeave={() => { carouselPaused.current = false; }}
          >
            <button
              className="carousel-arrow carousel-prev"
              onClick={() => setCurrentSlide(prev => (prev <= 0 ? MAX_SLIDE : prev - 1))}
              aria-label="Previous testimonials"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 18l-6-6 6-6"/></svg>
            </button>
            <div className="carousel-track-wrapper">
              <div className="carousel-track" style={{ transform: `translateX(-${currentSlide * (100 / SLIDES_VISIBLE)}%)` }}>
                {[
                  { quote: 'I used to waste 20 minutes hunting for one number across client files. Now I just ask and get the answer with the exact page cited. Took me about a day to wonder how I worked without it.', photo: 'https://i.pravatar.cc/96?img=12', name: 'James K.', title: 'Tax Partner, Regional Firm' },
                  { quote: 'The consent tracking alone was worth it. I was managing 7216 compliance in spreadsheets, which was a nightmare. Having it built in with e-signatures saves me hours every month.', photo: 'https://i.pravatar.cc/96?img=32', name: 'Michelle L.', title: 'Solo Practitioner' },
                  { quote: 'I pull a client brief before every meeting now. One click and I have a full snapshot with sources cited. My clients think I have a photographic memory.', photo: 'https://i.pravatar.cc/96?img=25', name: 'Sarah C.', title: 'Advisory Director' },
                  { quote: 'We got the whole firm set up in under an hour. The email sync alone saves us five hours a week. Every client conversation gets indexed and you can search across all of them.', photo: 'https://i.pravatar.cc/96?img=51', name: 'Robert P.', title: 'Managing Partner' },
                  { quote: 'I was skeptical about using AI for tax work. But every answer points to the exact document and page, so I can verify anything right away. That sold me.', photo: 'https://i.pravatar.cc/96?img=47', name: 'Amanda N.', title: 'Senior Tax Manager' },
                  { quote: 'The tax strategy module caught three things I missed in my own review. Paid for itself in the first week with one client.', photo: 'https://i.pravatar.cc/96?img=53', name: 'David W.', title: 'CPA, Boutique Firm' },
                ].map((t, i) => (
                  <div key={i} className="carousel-slide">
                    <div className="testimonial-card">
                      <p className="testimonial-quote">&ldquo;{t.quote}&rdquo;</p>
                      <div className="testimonial-author">
                        <img src={t.photo} alt="" style={{ width: 48, height: 48, borderRadius: '50%', objectFit: 'cover', flexShrink: 0 }} />
                        <div>
                          <div className="testimonial-name">{t.name}</div>
                          <div className="testimonial-title">{t.title}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <button
              className="carousel-arrow carousel-next"
              onClick={() => setCurrentSlide(prev => (prev >= MAX_SLIDE ? 0 : prev + 1))}
              aria-label="Next testimonials"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6"/></svg>
            </button>
          </div>
          <div className="carousel-dots">
            {Array.from({ length: MAX_SLIDE + 1 }).map((_, i) => (
              <button
                key={i}
                className={`carousel-dot${currentSlide === i ? ' active' : ''}`}
                onClick={() => setCurrentSlide(i)}
                aria-label={`Go to slide ${i + 1}`}
              />
            ))}
          </div>
        </div>

        {/* Security & Compliance */}
        <div className="security-section" data-reveal>
          <p className="overline">Security &amp; Compliance</p>
          <h2>Bank-level protection,<br /><em>built for tax</em></h2>
          <div className="security-grid">
            <div className="security-card">
              <div className="security-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 2L3 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5z"/></svg>
              </div>
              <h3>SOC 2 Type II Infrastructure</h3>
              <p>Hosted on certified infrastructure with continuous monitoring, access controls, and annual third-party audits.</p>
            </div>
            <div className="security-card">
              <div className="security-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
              </div>
              <h3>AES-256 Encryption</h3>
              <p>All data encrypted at rest and in transit. TLS 1.2+ for every connection. Your files are never stored unencrypted.</p>
            </div>
            <div className="security-card">
              <div className="security-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M20 6L9 17l-5-5"/><path d="M12 2L3 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5z"/></svg>
              </div>
              <h3>IRC {'\u00a7'}7216 Compliant</h3>
              <p>Built-in consent management with IRS-mandated language, e-signatures, expiration tracking, and full audit trails.</p>
            </div>
            <div className="security-card">
              <div className="security-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/><path d="M2 12h20M12 2c2.5 2.5 4 6 4 10s-1.5 7.5-4 10c-2.5-2.5-4-6-4-10s1.5-7.5 4-10z"/></svg>
              </div>
              <h3>US-Based Data Centers</h3>
              <p>All client data stored exclusively in US data centers. No offshore processing. No cross-border data transfers.</p>
            </div>
            <div className="security-card">
              <div className="security-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 15v2m0 0a2 2 0 100-4 2 2 0 000 4z"/><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
              </div>
              <h3>Zero Data Retention AI</h3>
              <p>AI providers process queries via commercial APIs with zero data retention. Your data is never used to train models.</p>
            </div>
            <div className="security-card">
              <div className="security-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 12h6M9 16h6M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9l-7-7z"/><path d="M13 2v7h7"/></svg>
              </div>
              <h3>AICPA Aligned</h3>
              <p>Designed around AICPA professional standards for technology use in accounting practice. Audit-ready from day one.</p>
            </div>
          </div>
        </div>

        {/* Pricing */}
        <section className="pricing" id="pricing">
          <div className="pricing-inner">
            <p className="overline" data-reveal>Pricing</p>
            <div className="billing-toggle" data-reveal>
              <div className="toggle-pill">
                <button
                  className={`toggle-opt${!annualBilling ? ' active' : ''}`}
                  onClick={() => setAnnualBilling(false)}
                >Monthly</button>
                <button
                  className={`toggle-opt${annualBilling ? ' active' : ''}`}
                  onClick={() => setAnnualBilling(true)}
                >Annual</button>
              </div>
              {annualBilling && <span className="save-badge">Save 20%</span>}
            </div>
            <h2 data-reveal>Plans that grow with your practice</h2>
            <div className="price-grid" data-reveal>
              <div className="p-card">
                <div className="p-tier">Free</div>
                <div className="p-price">$0 <span className="mo">/mo</span></div>
                <div className="p-desc">Get started. No credit card.</div>
                <ul className="p-list">
                  <li>5 clients</li>
                  <li>Unlimited documents</li>
                  <li>50 AI queries/month</li>
                  <li>10 extension captures/day</li>
                  <li>Standard AI</li>
                </ul>
                <Link href="/sign-in" className="p-btn p-btn-ghost">Start free</Link>
              </div>
              <div className="p-card">
                <div className="p-tier">Starter</div>
                <div className="p-price">${starterPrice} <span className="mo">/mo</span></div>
                {annualBilling && <div className="p-billed">billed $948/year</div>}
                <div className="p-desc">Solo practitioners getting organized.</div>
                <ul className="p-list">
                  <li>25 clients</li>
                  <li>500 documents</li>
                  <li>500 AI queries/month</li>
                  <li>50 extension captures/day</li>
                  <li>All integrations</li>
                </ul>
                <Link href="/sign-in" className="p-btn p-btn-ghost">Start 14-day trial</Link>
              </div>
              <div className="p-card featured">
                <div className="p-tier">Professional</div>
                <div className="p-price">${proPrice} <span className="mo">/mo</span></div>
                {annualBilling && <div className="p-billed">billed $1,428/year</div>}
                <div className="p-desc">Growing firms with 10+ clients.</div>
                <ul className="p-list">
                  <li>100 clients</li>
                  <li>5,000 documents</li>
                  <li>Advanced AI analysis</li>
                  <li>200 extension captures/day</li>
                  <li>Smart alerts + compliance</li>
                </ul>
                <Link href="/sign-in" className="p-btn p-btn-primary">Start 14-day trial</Link>
              </div>
              <div className="p-card">
                <div className="p-tier">Firm</div>
                <div className="p-price">$349 <span className="mo">/mo</span></div>
                <div className="p-desc">$349 base (3 seats) + $79/seat.</div>
                <ul className="p-list">
                  <li>Unlimited everything</li>
                  <li>Unlimited extension captures</li>
                  <li>Premium AI suite</li>
                  <li>Dedicated onboarding</li>
                  <li>Client allocation</li>
                </ul>
                <Link href="/sign-in" className="p-btn p-btn-ghost">Contact us</Link>
              </div>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <div className="faq-section">
          <p className="overline" data-reveal>FAQ</p>
          <h2 data-reveal>Common questions</h2>
          <div className="faq-list" data-reveal>
            {faqData.map((item, i) => (
              <div key={i} className={`faq-item${openFaq === i ? ' open' : ''}`}>
                <button className="faq-q" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
                  <span>{item.q}</span>
                  <span className="faq-icon">{openFaq === i ? '\u00d7' : '+'}</span>
                </button>
                {openFaq === i && (
                  <div className="faq-a">{item.a}</div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Final CTA */}
        <div className="finale">
          <p className="overline" data-reveal>Ready?</p>
          <h2 data-reveal>Stop searching.<br />Start <em>advising.</em></h2>
          <div className="finale-rule" data-reveal />
          <p data-reveal>Free tier includes 5 clients and unlimited documents. No credit card required. Set up in under two minutes.</p>
          <Link href="/sign-in" className="cta-btn" data-reveal>
            Get started for free <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 8h10M9 4l4 4-4 4"/></svg>
          </Link>
          <p className="trust" data-reveal><span>{'\u2605\u2605\u2605\u2605\u2605'}</span>&ensp; Trusted by financial professionals nationwide</p>
        </div>

        {/* Footer */}
        <footer>
          <div className="foot-container">
            <div className="foot-grid">
              <div className="foot-brand">
                <div className="foot-logo">Call<span>wen</span></div>
                <p className="foot-tagline">AI-powered document intelligence for financial professionals. Built by CPAs, for CPAs.</p>
                <a href="mailto:support@callwen.com" className="foot-email">support@callwen.com</a>
              </div>
              <div className="foot-col">
                <h4>Product</h4>
                <a href="#features">Features</a>
                <a href="#pricing">Pricing</a>
                <a href="#features">Integrations</a>
                <a href="#comparison">Security</a>
              </div>
              <div className="foot-col">
                <h4>Company</h4>
                <a href="#features">About</a>
                <span className="foot-soon">Blog</span>
                <span className="foot-soon">Careers</span>
                <a href="mailto:support@callwen.com">Contact</a>
              </div>
              <div className="foot-col">
                <h4>Legal</h4>
                <Link href="/privacy">Privacy Policy</Link>
                <Link href="/terms">Terms of Service</Link>
                <Link href="/privacy">Cookie Policy</Link>
                <a href="mailto:security@callwen.com">Security Overview</a>
              </div>
            </div>
            <div className="foot-bottom">
              <div className="foot-copy">{'\u00a9'} 2026 Callwen, Inc. All rights reserved.</div>
              <div className="foot-social">
                <a href="#" aria-label="LinkedIn"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg></a>
                <a href="#" aria-label="X"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>
              </div>
            </div>
          </div>
        </footer>
      </div>

      {/* Cookie consent banner */}
      {showCookieBanner && (
        <div className="cookie-banner">
          <div className="cookie-inner">
            <p className="cookie-text">
              We use essential cookies to make our site work. We may also use non-essential cookies to improve your experience. By clicking &ldquo;Accept&rdquo;, you agree to our use of <Link href="/privacy" className="cookie-link">cookies</Link>.
            </p>
            <div className="cookie-buttons">
              <button className="cookie-btn cookie-decline" onClick={() => handleCookieConsent(false)}>Decline</button>
              <button className="cookie-btn cookie-accept" onClick={() => handleCookieConsent(true)}>Accept</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ─── CSS ─── */
const landingCSS = `
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
:root {
  --bg-deep: #0c0e13;--bg-mid: #12151c;--bg-surface: #181c25;--bg-card: #1e222e;
  --accent: #c9944a;--accent-light: #e8b06a;--accent-glow: rgba(201,148,74,0.08);
  --teal: #5bb8af;--teal-dim: rgba(91,184,175,0.15);
  --white: #f0ede6;--white-dim: #b0aba4;--white-faint: #6a6662;
  --serif: 'Cormorant Garamond', Georgia, serif;
  --sans: 'Outfit', -apple-system, sans-serif;
}
html { scroll-behavior: smooth; }
body { background: var(--bg-deep); color: var(--white); font-family: var(--sans); font-weight: 300; overflow-x: hidden; -webkit-font-smoothing: antialiased; }
::selection { background: var(--accent); color: var(--bg-deep); }
#three-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0; pointer-events: none; }
.page-content { position: relative; z-index: 1; }

.nav { position: fixed; top: 0; left: 0; right: 0; z-index: 100; padding: 20px 0; transition: all 0.5s cubic-bezier(0.4,0,0.2,1); }
.nav.scrolled { background: rgba(12,14,19,0.88); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); padding: 14px 0; border-bottom: 1px solid rgba(201,148,74,0.08); }
.nav-inner { max-width: 1200px; margin: 0 auto; padding: 0 2rem; display: flex; align-items: center; justify-content: space-between; }
.nav-logo { font-family: var(--serif); font-size: 1.5rem; font-weight: 600; color: var(--white); }
.nav-logo span { color: var(--accent); }
.nav-links { display: flex; align-items: center; gap: 2rem; }
.nav-links a { font-size: 0.85rem; font-weight: 400; color: var(--white-dim); text-decoration: none; letter-spacing: 0.04em; transition: color 0.25s; }
.nav-links a:hover { color: var(--white); }
.nav-cta { padding: 10px 24px !important; background: var(--accent) !important; color: var(--bg-deep) !important; font-weight: 500 !important; border-radius: 6px; transition: all 0.25s !important; }
.nav-cta:hover { background: var(--accent-light) !important; transform: translateY(-1px); }

/* Hamburger menu */
.hamburger { display: none; background: none; border: none; cursor: pointer; padding: 8px; flex-direction: column; gap: 5px; z-index: 101; }
.hamburger span { display: block; width: 22px; height: 2px; background: var(--white); border-radius: 1px; transition: all 0.3s ease; }
.hamburger.open span:nth-child(1) { transform: rotate(45deg) translate(5px, 5px); }
.hamburger.open span:nth-child(2) { opacity: 0; }
.hamburger.open span:nth-child(3) { transform: rotate(-45deg) translate(5px, -5px); }

.mobile-menu { display: none; background: rgba(12,14,19,0.95); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); border-bottom: 1px solid rgba(255,255,255,0.05); }
.mobile-menu a { display: block; padding: 1rem 2rem; font-size: 0.9rem; font-weight: 400; color: var(--white-dim); text-decoration: none; border-bottom: 1px solid rgba(255,255,255,0.05); transition: color 0.25s; }
.mobile-menu a:hover { color: var(--white); }
.mobile-menu-cta { background: var(--accent) !important; color: var(--bg-deep) !important; font-weight: 500 !important; text-align: center; margin: 1rem; border-radius: 6px; border-bottom: none !important; }

.splash { min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; position: relative; padding: 0 2rem; }
.hero-split { display: flex; align-items: center; gap: 4rem; max-width: 1200px; width: 100%; }
.hero-left { flex: 1; text-align: left; }
.hero-right { flex: 1; display: flex; justify-content: center; opacity: 0; animation: fadeUp 0.8s 0.9s forwards; }
.hero-player { position: relative; width: 100%; border-radius: 14px; overflow: hidden; border: 1px solid rgba(201,148,74,0.15); box-shadow: 0 20px 60px rgba(0,0,0,0.4), 0 0 40px rgba(201,148,74,0.06); transform: perspective(800px) rotateY(-2deg); transition: transform 0.4s ease; cursor: pointer; }
.hero-player:hover { transform: perspective(800px) rotateY(0deg) scale(1.01); }
.hero-video { display: block; width: 100%; height: auto; }
.hero-play-btn { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(12,14,19,0.5); border: none; border-radius: 50%; width: 56px; height: 56px; display: flex; align-items: center; justify-content: center; color: rgba(240,237,230,0.85); cursor: pointer; transition: all 0.3s ease; backdrop-filter: blur(8px); }
.hero-play-btn:hover { background: rgba(201,148,74,0.3); color: var(--white); transform: translate(-50%, -50%) scale(1.1); }
.hero-play-btn svg { width: 48px; height: 48px; }
.hero-badge { display: inline-flex; align-items: center; gap: 8px; padding: 7px 18px; border-radius: 99px; font-size: 0.78rem; font-weight: 500; background: var(--accent-glow); color: var(--accent-light); border: 1px solid rgba(201,148,74,0.18); margin-bottom: 2.5rem; opacity: 0; animation: fadeUp 0.8s 0.3s forwards; backdrop-filter: blur(8px); }
.hero-badge .pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: pulseAnim 2s ease infinite; }
@keyframes pulseAnim { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.4;transform:scale(1.6)} }
.splash h1 { font-family: var(--serif); font-size: clamp(2.5rem,5vw,4.5rem); font-weight: 400; line-height: 1.05; letter-spacing: -0.02em; margin-bottom: 1.5rem; opacity: 0; animation: fadeUp 0.8s 0.45s forwards; }
.splash h1 em { font-style: italic; color: var(--accent-light); }
.splash .subtitle { font-size: clamp(1rem,2vw,1.2rem); font-weight: 400; color: var(--white-dim); max-width: 520px; line-height: 1.7; margin: 0; opacity: 0; animation: fadeUp 0.8s 0.6s forwards; }
.hero-buttons { display: flex; gap: 12px; justify-content: flex-start; margin-top: 2.5rem; opacity: 0; animation: fadeUp 0.8s 0.75s forwards; }
.btn { display: inline-flex; align-items: center; gap: 8px; padding: 14px 28px; border-radius: 8px; font-family: var(--sans); font-size: 0.9rem; font-weight: 500; border: none; cursor: pointer; text-decoration: none; transition: all 0.25s ease; }
.btn-primary { background: var(--accent); color: var(--bg-deep); }
.btn-primary:hover { background: var(--accent-light); transform: translateY(-1px); box-shadow: 0 8px 40px rgba(201,148,74,0.25); }
.btn-ghost { background: rgba(255,255,255,0.04); color: var(--white); border: 1px solid rgba(255,255,255,0.08); backdrop-filter: blur(4px); }
.btn-ghost:hover { background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.14); }
.btn svg { width: 16px; height: 16px; flex-shrink: 0; }
.splash .rule { width: 50px; height: 1px; background: var(--accent); margin: 2.5rem auto 0; opacity: 0; animation: fadeUp 0.8s 0.9s forwards; }
.scroll-hint { position: absolute; bottom: 2.5rem; font-size: 0.7rem; letter-spacing: 0.3em; text-transform: uppercase; color: var(--white-faint); opacity: 0; animation: fadeUp 0.8s 1.1s forwards; }
.scroll-hint::after { content: ''; display: block; width: 1px; height: 36px; background: var(--accent); margin: 0.6rem auto 0; animation: scrollPulse 2s ease-in-out infinite; }
@keyframes scrollPulse { 0%,100%{opacity:0.2;transform:scaleY(0.5)} 50%{opacity:0.8;transform:scaleY(1)} }
@keyframes fadeUp { from{opacity:0;transform:translateY(24px)} to{opacity:1;transform:translateY(0)} }

/* Trust badges */
.trust-badges-section { padding: 48px 2rem 56px; text-align: center; border-top: 1px solid rgba(201,148,74,0.06); border-bottom: 1px solid rgba(201,148,74,0.06); background: rgba(12,14,19,0.5); }
.trust-badges-label { font-family: var(--sans); font-size: 0.68rem; font-weight: 500; letter-spacing: 0.25em; text-transform: uppercase; color: #c9944a; margin-bottom: 36px; }
.trust-badges-row { display: flex; justify-content: center; align-items: flex-start; gap: 48px; flex-wrap: wrap; max-width: 960px; margin: 0 auto; }
.trust-badge { display: flex; flex-direction: column; align-items: center; gap: 10px; opacity: 0.7; transition: opacity 0.3s ease; cursor: default; }
.trust-badge:hover { opacity: 1; }
.trust-badge svg { width: 38px; height: 38px; }
.trust-badge-label { font-family: var(--sans); font-size: 0.65rem; font-weight: 400; color: #8a8680; letter-spacing: 0.04em; line-height: 1.35; max-width: 110px; text-align: center; }


[data-reveal] { opacity: 0; transform: translateY(30px); transition: opacity 0.7s cubic-bezier(0.4,0,0.2,1), transform 0.7s cubic-bezier(0.4,0,0.2,1); }
[data-reveal].visible { opacity: 1; transform: translateY(0); }

.sections { max-width: 1200px; margin: 0 auto; }
.section { min-height: 100vh; display: flex; align-items: center; justify-content: flex-start; gap: 4rem; padding: 6rem 2rem; }
.section.right { flex-direction: row-reverse; text-align: right; }
.section .number { font-family: var(--serif); font-size: clamp(5rem,10vw,9rem); font-weight: 700; color: var(--accent); opacity: 0.12; line-height: 1; flex-shrink: 0; }
.section .content { max-width: 560px; }
.section h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3.2rem); font-weight: 400; margin-bottom: 1.5rem; line-height: 1.1; }
.section h2 em { font-style: italic; color: var(--accent-light); }
.section p { font-size: clamp(0.95rem,1.5vw,1.1rem); line-height: 1.8; color: var(--white-dim); font-weight: 400; }
.section .tag { display: inline-block; margin-top: 1.5rem; font-size: 0.68rem; letter-spacing: 0.25em; text-transform: uppercase; color: var(--teal); border: 1px solid var(--teal-dim); padding: 0.5em 1.2em; border-radius: 3px; }

.section-visual { flex-shrink: 0; width: 340px; height: 230px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.04); background: rgba(18,21,28,0.7); backdrop-filter: blur(12px); position: relative; overflow: hidden; }
.section-visual::before { content: ''; position: absolute; inset: 0; background: linear-gradient(135deg, rgba(201,148,74,0.04) 0%, transparent 60%); }
.section-visual-img { width: 480px; height: 320px; box-shadow: 0 8px 32px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.06); }
.section-visual-img::before { display: none; }
.section-visual-consent { height: auto; max-height: 240px; display: flex; align-items: center; justify-content: center; }
.section-visual-ext { width: 280px; height: 420px; }
.vis-team { display: flex; align-items: center; justify-content: center; height: 100%; gap: 12px; }
.team-avatar { width: 44px; height: 44px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 500; border: 2px solid rgba(18,21,28,0.8); }
.team-avatar:nth-child(1) { background: rgba(201,148,74,0.2); color: var(--accent-light); margin-right: -8px; z-index: 3; }
.team-avatar:nth-child(2) { background: rgba(91,184,175,0.2); color: var(--teal); margin-right: -8px; z-index: 2; }
.team-avatar:nth-child(3) { background: rgba(139,123,245,0.2); color: #a99bf5; z-index: 1; }

/* Testimonial Carousel */
.testimonials-section { padding: 6rem 2rem; text-align: center; }
.testimonials-section .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 1.5rem; }
.testimonials-section h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 3.5rem; }
.carousel-container { position: relative; max-width: 1100px; margin: 0 auto; display: flex; align-items: center; gap: 1rem; }
.carousel-track-wrapper { overflow: hidden; flex: 1; }
.carousel-track { display: flex; transition: transform 0.5s cubic-bezier(0.4,0,0.2,1); }
.carousel-slide { min-width: calc(100% / 3); padding: 0 0.75rem; box-sizing: border-box; }
.carousel-arrow { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 50%; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.25s; flex-shrink: 0; }
.carousel-arrow:hover { background: rgba(255,255,255,0.08); border-color: rgba(201,148,74,0.3); }
.carousel-arrow svg { width: 20px; height: 20px; color: var(--white-dim); }
.carousel-dots { display: flex; justify-content: center; gap: 8px; margin-top: 2rem; }
.carousel-dot { width: 8px; height: 8px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.15); background: transparent; cursor: pointer; transition: all 0.25s; padding: 0; }
.carousel-dot.active { background: var(--accent); border-color: var(--accent); }
.carousel-dot:hover { border-color: var(--accent); }
.testimonial-card { background: rgba(18,21,28,0.85); backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.04); padding: 2rem; border-radius: 12px; text-align: left; height: 100%; display: flex; flex-direction: column; }
.testimonial-quote { font-size: 0.95rem; line-height: 1.7; color: var(--white-dim); font-weight: 400; font-style: italic; flex: 1; }
.testimonial-author { display: flex; align-items: center; gap: 12px; margin-top: 1.5rem; }
.testimonial-avatar { width: 48px; height: 48px; border-radius: 50%; flex-shrink: 0; }
.testimonial-name { font-size: 0.85rem; font-weight: 500; color: var(--white); }
.testimonial-title { font-size: 0.78rem; color: var(--white-faint); }

/* Security & Compliance */
.security-section { padding: 6rem 2rem; text-align: center; border-top: 1px solid rgba(255,255,255,0.03); }
.security-section .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 1.5rem; }
.security-section h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 3.5rem; line-height: 1.15; }
.security-section h2 em { font-style: italic; color: var(--accent-light); }
.security-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 1px; background: rgba(255,255,255,0.03); border-radius: 12px; overflow: hidden; max-width: 1100px; margin: 0 auto; }
.security-card { background: rgba(18,21,28,0.85); backdrop-filter: blur(8px); padding: 2.5rem 2rem; text-align: left; }
.security-icon { width: 40px; height: 40px; border-radius: 8px; background: var(--teal-dim); display: flex; align-items: center; justify-content: center; margin-bottom: 1.2rem; }
.security-icon svg { width: 20px; height: 20px; stroke: var(--teal); }
.security-card h3 { font-family: var(--sans); font-size: 0.95rem; font-weight: 500; color: var(--white); margin-bottom: 0.6rem; }
.security-card p { font-size: 0.82rem; line-height: 1.7; color: var(--white-dim); font-weight: 400; }

/* Cost Comparison */
.cost-section { padding: 6rem 2rem; border-top: 1px solid rgba(255,255,255,0.03); }
.cost-inner { max-width: 820px; margin: 0 auto; text-align: center; }
.cost-section .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 1.5rem; }
.cost-section h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 1rem; }
.cost-subtitle { font-size: 0.92rem; color: var(--white-dim); margin-bottom: 3rem; font-weight: 400; }
.cost-table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 2.5rem; }
.cost-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; overflow: hidden; background: rgba(18,21,28,0.85); backdrop-filter: blur(8px); }
.cost-th { padding: 1.2rem 1.5rem; font-size: 0.7rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--white-dim); background: rgba(24,28,37,0.9); text-align: left; font-weight: 500; }
.cost-th.callwen-col { text-align: center; }
.callwen-badge { display: inline-block; background: var(--accent); color: var(--bg-deep); font-size: 0.65rem; font-weight: 600; padding: 3px 10px; border-radius: 99px; letter-spacing: 0.1em; }
.cost-row { border-bottom: 1px solid rgba(255,255,255,0.03); }
.cost-td { padding: 1rem 1.5rem; font-size: 0.85rem; }
.cost-td.tool-col { color: var(--white-dim); text-align: left; font-weight: 400; }
.cost-td.price-col { color: var(--white-faint); text-align: left; font-weight: 400; white-space: nowrap; }
.cost-td.callwen-col { text-align: center; }
.cost-check { width: 20px; height: 20px; color: var(--accent); display: inline-block; vertical-align: middle; }
.cost-total-row { background: rgba(201,148,74,0.06); border-top: 1px solid rgba(201,148,74,0.15); }
.cost-total-label { font-weight: 600; color: var(--white); }
.cost-total-price { font-weight: 600; color: var(--white); white-space: nowrap; }
.cost-callwen-price { font-family: var(--serif); font-size: 1.1rem; font-weight: 600; color: var(--accent); }
.cost-per { font-size: 0.72rem; font-weight: 400; color: var(--white-dim); font-family: var(--sans); }
.cost-cta { display: inline-block; font-size: 0.88rem; font-weight: 500; color: var(--accent); text-decoration: none; transition: color 0.2s; }
.cost-cta:hover { color: var(--accent-light); }

/* Impact Cards */
.impact-section { padding: 6rem 2rem; border-top: 1px solid rgba(255,255,255,0.03); }
.impact-inner { max-width: 1000px; margin: 0 auto; text-align: center; }
.impact-section .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 1.5rem; }
.impact-section h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 3.5rem; }
.impact-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 1px; background: rgba(255,255,255,0.03); border-radius: 12px; overflow: hidden; }
.impact-card { background: rgba(18,21,28,0.85); backdrop-filter: blur(8px); padding: 3rem 2rem; text-align: center; }
.impact-number { font-family: var(--serif); font-size: 3rem; font-weight: 600; color: var(--accent); line-height: 1; margin-bottom: 0.4rem; }
.impact-unit { font-size: 0.82rem; font-weight: 500; color: var(--white); text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 1.2rem; }
.impact-desc { font-size: 0.85rem; color: var(--white-dim); line-height: 1.7; font-weight: 400; max-width: 280px; margin: 0 auto; }

.pricing { padding: 8rem 2rem; }
.pricing-inner { max-width: 1100px; margin: 0 auto; text-align: center; }
.pricing .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 1.5rem; }
.pricing h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 3.5rem; }

/* Billing toggle */
.billing-toggle { display: flex; align-items: center; justify-content: center; gap: 12px; margin-bottom: 1.5rem; }
.toggle-pill { display: inline-flex; border-radius: 99px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08); padding: 3px; }
.toggle-opt { padding: 8px 20px; border-radius: 99px; font-family: var(--sans); font-size: 0.8rem; font-weight: 500; border: none; cursor: pointer; transition: all 0.25s; background: transparent; color: var(--white-dim); }
.toggle-opt.active { background: var(--accent); color: var(--bg-deep); }
.save-badge { display: inline-block; font-size: 0.7rem; background: var(--teal-dim); color: var(--teal); padding: 3px 10px; border-radius: 99px; font-weight: 500; }

.price-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 1px; background: rgba(255,255,255,0.03); border-radius: 12px; overflow: hidden; }
.p-card { background: rgba(18,21,28,0.85); backdrop-filter: blur(8px); padding: 2.5rem 2rem; text-align: left; display: flex; flex-direction: column; position: relative; }
.p-card.featured { background: rgba(24,28,37,0.9); border-top: 2px solid var(--accent); }
.p-card.featured::before { content: 'Most popular'; position: absolute; top: -2px; left: 50%; transform: translate(-50%,-100%); font-size: 0.65rem; font-weight: 500; letter-spacing: 0.15em; text-transform: uppercase; color: var(--bg-deep); background: var(--accent); padding: 4px 14px; border-radius: 4px 4px 0 0; }
.p-tier { font-size: 0.75rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--white-dim); margin-bottom: 1rem; }
.p-price { font-family: var(--serif); font-size: 2.8rem; font-weight: 600; margin-bottom: 0.3rem; }
.p-price .mo { font-size: 0.9rem; font-weight: 300; color: var(--white-dim); font-family: var(--sans); }
.p-billed { font-size: 0.72rem; color: var(--teal); margin-bottom: 0.3rem; font-weight: 400; }
.p-desc { font-size: 0.82rem; color: var(--white-dim); margin-bottom: 1.8rem; line-height: 1.5; }
.p-list { list-style: none; margin-bottom: 2rem; flex: 1; }
.p-list li { font-size: 0.82rem; color: #ccc7bf; padding: 0.45rem 0; border-bottom: 1px solid rgba(255,255,255,0.03); position: relative; padding-left: 1.2rem; }
.p-list li::before { content: '·'; position: absolute; left: 0; color: var(--accent); font-weight: 700; }
.p-btn { display: block; text-align: center; padding: 12px; border-radius: 6px; font-size: 0.82rem; font-weight: 500; text-decoration: none; transition: all 0.25s; }
.p-btn-primary { background: var(--accent); color: var(--bg-deep); }
.p-btn-primary:hover { background: var(--accent-light); transform: translateY(-1px); }
.p-btn-ghost { background: rgba(255,255,255,0.04); color: var(--white); border: 1px solid rgba(255,255,255,0.08); }
.p-btn-ghost:hover { background: rgba(255,255,255,0.08); }

/* FAQ */
.faq-section { padding: 6rem 2rem; text-align: center; border-top: 1px solid rgba(255,255,255,0.04); }
.faq-section .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 1.5rem; }
.faq-section h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 3.5rem; }
.faq-list { max-width: 700px; margin: 0 auto; text-align: left; }
.faq-item { border-bottom: 1px solid rgba(255,255,255,0.05); }
.faq-q { display: flex; justify-content: space-between; align-items: center; width: 100%; padding: 1.5rem 0; cursor: pointer; background: none; border: none; font-family: var(--sans); font-size: 1rem; font-weight: 400; color: var(--white); transition: color 0.25s; text-align: left; }
.faq-q:hover { color: var(--accent-light); }
.faq-icon { color: var(--accent); font-size: 1.2rem; flex-shrink: 0; margin-left: 1rem; transition: transform 0.3s; }
.faq-a { padding: 0 0 1.5rem; font-size: 0.9rem; line-height: 1.8; color: var(--white-dim); font-weight: 400; }

.finale { min-height: 80vh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 6rem 2rem; }
.finale .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 2rem; }
.finale h2 { font-family: var(--serif); font-size: clamp(2.5rem,6vw,4.5rem); font-weight: 400; line-height: 1.1; margin-bottom: 1.5rem; color: var(--white); }
.finale-rule { width: 50px; height: 1px; background: var(--accent); margin: 0 auto 1.5rem; opacity: 0.6; }
.finale h2 em { font-style: italic; color: var(--accent-light); }
.finale p { max-width: 480px; margin: 0 auto; font-size: 1.05rem; line-height: 1.7; color: var(--white-dim); font-weight: 400; }
.finale .cta-btn { display: inline-flex; align-items: center; gap: 10px; margin-top: 2.5rem; padding: 16px 36px; font-family: var(--sans); font-size: 0.9rem; font-weight: 500; color: var(--bg-deep); background: var(--accent); border: none; border-radius: 8px; cursor: pointer; text-decoration: none; transition: all 0.3s ease; }
.finale .cta-btn:hover { background: var(--accent-light); transform: translateY(-2px); box-shadow: 0 12px 48px rgba(201,148,74,0.25); }
.finale .cta-btn svg { width: 16px; height: 16px; }
.finale .trust { margin-top: 1.5rem; font-size: 0.78rem; color: var(--white-dim); }
.finale .trust span { color: var(--accent); }

/* Cookie consent banner */
.cookie-banner { position: fixed; bottom: 0; left: 0; right: 0; z-index: 200; background: rgba(18,21,28,0.95); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border-top: 1px solid rgba(255,255,255,0.06); padding: 1rem 2rem; animation: slideUp 0.4s ease; }
@keyframes slideUp { from { opacity: 0; transform: translateY(100%); } to { opacity: 1; transform: translateY(0); } }
.cookie-inner { max-width: 1200px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 2rem; }
.cookie-text { flex: 1; font-size: 0.82rem; color: var(--white-dim); font-weight: 400; line-height: 1.6; }
.cookie-link { color: var(--accent); text-decoration: none; }
.cookie-link:hover { text-decoration: underline; }
.cookie-buttons { display: flex; gap: 8px; flex-shrink: 0; }
.cookie-btn { padding: 8px 20px; border-radius: 6px; font-family: var(--sans); font-size: 0.8rem; font-weight: 500; cursor: pointer; transition: all 0.25s; border: none; }
.cookie-accept { background: var(--accent); color: var(--bg-deep); }
.cookie-accept:hover { background: var(--accent-light); }
.cookie-decline { background: transparent; border: 1px solid rgba(255,255,255,0.1); color: var(--white-dim); }
.cookie-decline:hover { background: rgba(255,255,255,0.05); }

footer { padding: 4rem 2rem 2rem; border-top: 1px solid rgba(255,255,255,0.05); background: rgba(12,14,19,0.95); }
.foot-container { max-width: 1200px; margin: 0 auto; }
.foot-grid { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 3rem; margin-bottom: 3rem; }
.foot-brand { }
.foot-logo { font-family: var(--serif); font-size: 1.5rem; font-weight: 600; color: var(--white); margin-bottom: 1rem; }
.foot-logo span { color: var(--accent); }
.foot-tagline { font-size: 0.82rem; color: var(--white-dim); max-width: 250px; line-height: 1.6; margin-bottom: 1rem; }
.foot-email { font-size: 0.8rem; color: var(--white-faint); text-decoration: none; transition: color 0.2s; }
.foot-email:hover { color: var(--white-dim); }
.foot-col { display: flex; flex-direction: column; gap: 0.6rem; }
.foot-col h4 { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.2em; color: var(--white); margin-bottom: 0.4rem; font-weight: 500; }
.foot-col a { font-size: 0.82rem; color: var(--white-faint); text-decoration: none; transition: color 0.2s; }
.foot-col a:hover { color: var(--white-dim); }
.foot-soon { font-size: 0.82rem; color: var(--white-faint); opacity: 0.4; cursor: default; }
.foot-bottom { display: flex; align-items: center; justify-content: space-between; padding-top: 2rem; border-top: 1px solid rgba(255,255,255,0.05); }
.foot-copy { font-size: 0.75rem; color: var(--white-faint); }
.foot-social { display: flex; gap: 1rem; }
.foot-social a { color: var(--white-faint); transition: color 0.2s; }
.foot-social a:hover { color: var(--white-dim); }
.foot-social svg { width: 18px; height: 18px; }

@media (max-width:900px) {
  .nav-links { display: none; }
  .hamburger { display: flex; }
  .mobile-menu { display: block; }
  .section { flex-direction: column !important; text-align: left !important; gap: 2rem; min-height: auto; padding: 5rem 1.5rem; }
  .section .number { font-size: 4rem; align-self: flex-start; }
  .section-visual { width: 100%; max-width: 360px; }
  .section-visual-img { max-width: 480px; height: auto; }
  .section-visual-ext { width: 260px; max-width: 80%; height: auto; margin: 0 auto; }
  .impact-grid { grid-template-columns: 1fr; }
  .price-grid { grid-template-columns: 1fr 1fr; }
  .carousel-slide { min-width: 100%; }
  .carousel-arrow { display: none; }
  .security-grid { grid-template-columns: 1fr 1fr; }
  .foot-grid { grid-template-columns: 1fr 1fr; row-gap: 2rem; }
}
@media (max-width:767px) {
  #three-canvas { display: none; }
  .hero-split { flex-direction: column; gap: 2.5rem; text-align: center; }
  .hero-left { text-align: center; }
  .hero-buttons { justify-content: center; }
  .hero-player { transform: none; max-width: 480px; }
  .hero-player:hover { transform: none; }
}
@media (max-width:600px) {
  .price-grid { grid-template-columns: 1fr; }
  .hero-buttons { flex-direction: column; align-items: center; }
  .trust-badges-row { gap: 32px 24px; max-width: 320px; }
  .trust-badge svg { width: 32px; height: 32px; }
  .trust-badge-label { font-size: 0.6rem; max-width: 90px; }
  .security-grid { grid-template-columns: 1fr; }
  .cookie-inner { flex-direction: column; gap: 1rem; }
  .cookie-buttons { justify-content: flex-end; }
  .foot-grid { grid-template-columns: 1fr; }
  .foot-bottom { flex-direction: column; gap: 1rem; text-align: center; }
}
`;
