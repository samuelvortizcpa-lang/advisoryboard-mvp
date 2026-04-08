'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import Script from 'next/script';

const faqCategories = [
  {
    label: 'Platform & Features',
    items: [
      {
        q: 'How is Callwen different from meeting tools like Brieff or Jump AI?',
        a: 'Meeting tools like Brieff and Jump AI excel at structuring conversations and capturing notes \u2014 and they\u2019re great at what they do. Callwen operates at a different layer. We analyze your full client document corpus \u2014 tax returns, financial statements, meeting recordings, emails, client check-ins \u2014 and make it all queryable with AI. When you ask Callwen a question, you get answers sourced from years of client history, not just the last meeting. Think of it this way: meeting tools help you run a better conversation. Callwen ensures you have the right information to make that conversation count. Many firms use both \u2014 one for the workflow, one for the knowledge.',
      },
      {
        q: 'What kinds of questions can I ask Callwen?',
        a: 'Anything you\u2019d ask a colleague who memorized every client document. For example: \u201cWhat was John\u2019s AGI trend over the last 3 years?\u201d or \u201cWhat strategies are we missing for this S-Corp client?\u201d or \u201cWhat did my client say was keeping them up at night in their last check-in?\u201d or \u201cAre there any contradictions between the 2024 and 2023 returns?\u201d Callwen pulls answers from every document, check-in, conversation, and financial metric in the system \u2014 with source citations so you can verify.',
      },
      {
        q: 'What document types does Callwen support?',
        a: 'Callwen processes PDFs, scanned documents (via OCR), audio and video recordings (with automatic transcription), spreadsheets, and email files. It auto-classifies 12+ tax document types including Form 1040, W-2, K-1, 1099, 1120-S, 1065, 1041, and more. It also extracts 63 structured financial metrics from supported forms \u2014 so you can ask about specific numbers, not just general content.',
      },
      {
        q: 'How does the Tax Strategy Matrix work?',
        a: 'Callwen tracks 15+ common tax strategies per client \u2014 from QBI deductions to cost segregation studies to retirement plan contributions. Each strategy has an implementation status, estimated dollar impact, and year-over-year comparison. The AI can also auto-suggest applicable strategies based on a client\u2019s uploaded documents and financial profile.',
      },
      {
        q: 'What are Client Check-ins?',
        a: 'Check-ins are customizable questionnaires you send to clients before meetings \u2014 via email, no login required. Clients answer questions about how their business is going, what\u2019s changed, and what they want to discuss. Their responses feed directly into Callwen\u2019s AI, so every feature automatically has richer context about each client. Think of it as capturing the information that never makes it into a tax return.',
      },
    ],
  },
  {
    label: 'Getting Started',
    items: [
      {
        q: 'How long does it take to get set up?',
        a: 'Most users are up and running in under 5 minutes. Sign up, upload your first document, and start asking questions immediately. There\u2019s a guided onboarding wizard that walks you through creating your first client, uploading documents, and using the AI chat. No IT department needed.',
      },
      {
        q: 'Can I use Callwen with my existing tools?',
        a: 'Yes. Callwen integrates with Gmail, Outlook, Zoom, and Fathom for meeting recordings, and has a Chrome extension for capturing web content directly into client files. It complements your existing CRM, practice management software, and tax preparation tools \u2014 it doesn\u2019t replace them.',
      },
      {
        q: 'Can my whole team use Callwen?',
        a: 'Absolutely. Callwen supports multi-user organizations with role-based access, client assignments, and shared document libraries. The Firm tier includes 3 seats with additional seats at $79/month. Team members see only the clients assigned to them unless given broader access.',
      },
    ],
  },
  {
    label: 'Pricing & Plans',
    items: [
      {
        q: 'Is there a free plan?',
        a: 'Yes. The free tier includes 5 clients, unlimited document uploads, 50 AI queries per month, and 5 client check-ins per month. No credit card required. It\u2019s a fully functional version of the product \u2014 not a limited demo.',
      },
      {
        q: 'What\u2019s the difference between Standard, Advanced, and Premium AI analysis?',
        a: 'Standard analysis handles straightforward document lookups \u2014 \u201cWhat was this client\u2019s W-2 income?\u201d Advanced analysis handles comparisons and synthesis across multiple documents. Premium analysis provides strategic recommendations and tax planning insights. All tiers include all three levels \u2014 the difference is how many advanced and premium queries are included per month.',
      },
      {
        q: 'Can I change or cancel my plan?',
        a: 'Yes. All plans are month-to-month with no long-term contracts. You can upgrade, downgrade, or cancel at any time from your account settings. Annual plans offer a 20% discount and can also be cancelled.',
      },
      {
        q: 'Do you offer a trial?',
        a: 'The free tier is essentially an unlimited trial \u2014 5 clients, no time limit, no credit card. Use it as long as you want. When you\u2019re ready for more clients or more AI queries, upgrade to a paid plan.',
      },
    ],
  },
  {
    label: 'Security & Compliance',
    items: [
      {
        q: 'How secure is my data?',
        a: 'All data is encrypted at rest (AES-256) and in transit (TLS 1.3). Client documents are stored in US-based data centers via Supabase. All AI processing uses commercial APIs with zero data retention policies \u2014 your client data is never used to train AI models and is never stored by AI providers.',
      },
      {
        q: 'What is IRC Section 7216 and why does it matter?',
        a: 'Section 7216 of the Internal Revenue Code requires CPAs to obtain written taxpayer consent before disclosing or using tax return information with third-party services \u2014 including AI tools. Most AI platforms ignore this entirely. Callwen has built-in tiered consent tracking with e-signature workflow, so you can document compliance for every client before uploading their tax documents.',
      },
      {
        q: 'Who can see my clients\u2019 data?',
        a: 'Only authorized users in your organization. Callwen uses organization-scoped data isolation \u2014 your data is completely separate from every other firm on the platform. Within your org, you can control access at the client level through team assignments.',
      },
      {
        q: 'Does Callwen use my data to train AI models?',
        a: 'No. Your data is used exclusively to serve your queries. It is never shared with other customers, never used for model training, and never stored beyond what\u2019s needed to deliver your results. Our AI providers (used via API) have zero data retention agreements in place.',
      },
    ],
  },
];

export default function LandingPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const threeLoaded = useRef(false);

  // State for interactive elements
  const [menuOpen, setMenuOpen] = useState(false);
  const [annualBilling, setAnnualBilling] = useState(false);
  const [openFaq, setOpenFaq] = useState<string | null>(null);
  const [faqFilter, setFaqFilter] = useState<string | null>(null);
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
              <Link href="/sign-up" className="nav-cta">Get started free</Link>
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
              <Link href="/sign-up" className="mobile-menu-cta" onClick={() => setMenuOpen(false)}>Get started free</Link>
            </div>
          )}
        </nav>

        {/* Hero */}
        <section className="splash">
          <div className="hero-split">
            <div className="hero-left">
              <div className="hero-badge"><span className="pulse" /> AI Advisory Intelligence Platform</div>
              <h1>The AI that <em>knows</em><br />your clients as well<br />as you do.</h1>
              <p className="subtitle">Upload tax returns, meeting recordings, and client files. Ask any question. Get cited answers in seconds. Surface strategies you missed.</p>
              <div className="hero-buttons">
                <Link href="/sign-up" className="btn btn-primary">
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

        {/* Capability metrics strip */}
        <div className="trust-badges-section" data-reveal>
          <div className="metrics-row">
            <div className="metric-item">
              <span className="metric-number">63</span>
              <span className="metric-label">Financial Metrics Extracted</span>
            </div>
            <span className="metric-divider" />
            <div className="metric-item">
              <span className="metric-number">15+</span>
              <span className="metric-label">Tax Strategies Tracked</span>
            </div>
            <span className="metric-divider" />
            <div className="metric-item">
              <span className="metric-number">38</span>
              <span className="metric-label">Automated Deadlines</span>
            </div>
            <span className="metric-divider" />
            <div className="metric-item">
              <span className="metric-number">{'\u00a7'}7216</span>
              <span className="metric-label">Compliant</span>
            </div>
          </div>
        </div>

        {/* How it works */}
        <div className="workflow-section" data-reveal>
          <div className="workflow-inner">
            <h2 className="workflow-heading">How Callwen works</h2>
            <div className="workflow-grid">
              <div className="workflow-step">
                <div className="workflow-num">01</div>
                <div className="workflow-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/></svg>
                </div>
                <h3>Upload</h3>
                <p>Drop in tax returns, recordings, emails, or any client file. Callwen auto-classifies 12+ document types and extracts 63 financial metrics.</p>
              </div>
              <div className="workflow-step">
                <div className="workflow-num">02</div>
                <div className="workflow-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"/></svg>
                </div>
                <h3>Ask</h3>
                <p>Ask anything in plain English. Get cited answers sourced from every document in the client&apos;s history — not just the last one.</p>
              </div>
              <div className="workflow-step">
                <div className="workflow-num">03</div>
                <div className="workflow-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18"/></svg>
                </div>
                <h3>Discover</h3>
                <p>Callwen surfaces tax strategies you might have missed, flags data contradictions, and tracks financial trends across years.</p>
              </div>
              <div className="workflow-step">
                <div className="workflow-num">04</div>
                <div className="workflow-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                </div>
                <h3>Act</h3>
                <p>Auto-generate deadlines, send client check-ins, draft quarterly estimate emails, and export a complete practice book.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Feature sections */}
        <div className="sections" id="features">
          <div className="section left" data-reveal>
            <div className="number">01</div>
            <div className="content">
              <h2>Every document,<br /><em>instantly searchable</em></h2>
              <p>Upload tax returns, meeting recordings, emails, and financial statements. Callwen auto-classifies 12+ document types, extracts structured financial data, and makes everything queryable with AI — complete with source citations and confidence scores.</p>
              <span className="tag">Upload · Classify · Query</span>
            </div>
            <div className="section-visual section-visual-img" aria-hidden="true">
              <img
                src="/images/feature-01-documents.png"
                alt="Callwen document intelligence interface showing organized client documents with AI chat"
                style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top left', borderRadius: '12px' }}
              />
            </div>
          </div>

          <div className="section right" data-reveal>
            <div className="number">02</div>
            <div className="content">
              <h2>Walk into every meeting<br /><em>prepared</em></h2>
              <p>Send automated check-ins before client meetings. Clients complete them in minutes — no login required. Their responses feed directly into your AI, so every question you ask already knows what&apos;s keeping your client up at night.</p>
              <span className="tag">Check-ins · No login · AI-fed</span>
            </div>
            <div className="section-visual" aria-hidden="true">
              <div className="vis-checkin">
                <div className="vis-checkin-header">Quarterly Check-in</div>
                <div className="vis-checkin-rating">
                  <span className="vis-star filled">{'\u2605'}</span>
                  <span className="vis-star filled">{'\u2605'}</span>
                  <span className="vis-star filled">{'\u2605'}</span>
                  <span className="vis-star">{'\u2606'}</span>
                  <span className="vis-star">{'\u2606'}</span>
                </div>
                <div className="vis-checkin-quote">&ldquo;Concerned about the new lease terms affecting our deductions...&rdquo;</div>
                <div className="vis-checkin-badge">Completed</div>
              </div>
            </div>
          </div>

          <div className="section left" data-reveal>
            <div className="number">03</div>
            <div className="content">
              <h2>Strategies you&apos;d miss,<br /><em>surfaced automatically</em></h2>
              <p>Track 15+ tax strategies per client with implementation status and estimated dollar impact. Year-over-year comparison shows what&apos;s working. AI proactively suggests strategies based on the full document history.</p>
              <span className="tag">Strategies · Dollar impact · YoY</span>
            </div>
            <div className="section-visual" aria-hidden="true">
              <div className="vis-strategies">
                <div className="vis-strategy-row">
                  <span className="vis-strat-name">QBI Deduction</span>
                  <span className="vis-strat-status implemented">{'\u2713'} Implemented</span>
                  <span className="vis-strat-impact">$12,400 saved</span>
                </div>
                <div className="vis-strategy-row">
                  <span className="vis-strat-name">Cost Segregation</span>
                  <span className="vis-strat-status recommended">Recommended</span>
                  <span className="vis-strat-impact">~$8,200 potential</span>
                </div>
                <div className="vis-strategy-row">
                  <span className="vis-strat-name">R&amp;D Credit</span>
                  <span className="vis-strat-status recommended">Recommended</span>
                  <span className="vis-strat-impact">~$5,100 potential</span>
                </div>
              </div>
            </div>
          </div>

          <div className="section right" data-reveal>
            <div className="number">04</div>
            <div className="content">
              <h2>Your practice,<br /><em>ready to scale or sell</em></h2>
              <p>The Practice Book packages everything — financial trends, strategy history, communication logs, engagement health scores — into a professional export. Eliminate key-man risk and demonstrate advisory value to buyers, partners, or your future self.</p>
              <span className="tag">Practice Book · Health scores · Export</span>
            </div>
            <div className="section-visual" aria-hidden="true">
              <div className="vis-health">
                <div className="vis-health-gauge">
                  <svg viewBox="0 0 120 120">
                    <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
                    <circle cx="60" cy="60" r="50" fill="none" stroke="#5bb8af" strokeWidth="8" strokeDasharray="274" strokeDashoffset="36" strokeLinecap="round" transform="rotate(-90 60 60)" />
                    <text x="60" y="55" textAnchor="middle" fill="#f0ede6" fontSize="28" fontWeight="600" fontFamily="var(--serif)">87</text>
                    <text x="60" y="72" textAnchor="middle" fill="#8a8680" fontSize="10" fontFamily="var(--sans)">/100</text>
                  </svg>
                </div>
                <div className="vis-health-metrics">
                  <div className="vis-health-row"><span className="vis-health-label">Clients</span><span className="vis-health-val">42</span></div>
                  <div className="vis-health-row"><span className="vis-health-label">Avg Health</span><span className="vis-health-val">87</span></div>
                  <div className="vis-health-row"><span className="vis-health-label">Transition Ready</span><span className="vis-health-val">94%</span></div>
                </div>
              </div>
            </div>
          </div>

          <div className="section left" data-reveal>
            <div className="number">05</div>
            <div className="content">
              <h2>Never miss a deadline.<br /><em>Never chase a task.</em></h2>
              <p>Assign engagement templates and Callwen generates every quarterly estimate reminder, every return deadline, every document request. Threaded email drafts reference prior conversations and open items automatically.</p>
              <span className="tag">Deadlines · Reminders · Threaded emails</span>
            </div>
            <div className="section-visual" aria-hidden="true">
              <div className="vis-deadlines">
                <div className="vis-deadline-row">
                  <span className="vis-deadline-dot amber" />
                  <span className="vis-deadline-task">Q2 Estimated Payment</span>
                  <span className="vis-deadline-date">Jun 15</span>
                </div>
                <div className="vis-deadline-row">
                  <span className="vis-deadline-dot green" />
                  <span className="vis-deadline-task">1040 Extension</span>
                  <span className="vis-deadline-date">Oct 15</span>
                </div>
                <div className="vis-deadline-row">
                  <span className="vis-deadline-dot gray" />
                  <span className="vis-deadline-task">Year-End Review</span>
                  <span className="vis-deadline-date">Dec 1</span>
                </div>
              </div>
            </div>
          </div>

          <div className="section right" data-reveal id="extension">
            <div className="number">06</div>
            <div className="content">
              <h2>Context that<br /><em>compounds over time</em></h2>
              <p>Callwen remembers every conversation, detects contradictions across documents, and logs circumstance changes automatically. The longer you use it, the smarter it gets — like institutional memory that never leaves the firm.</p>
              <span className="tag">Memory · Contradictions · Sessions</span>
            </div>
            <div className="section-visual" aria-hidden="true">
              <div className="vis-memory">
                <div className="vis-memory-session">
                  <span className="vis-memory-icon">
                    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M7.5 8.25h5M7.5 11.25h3.5M17.5 10c0 4.14-3.36 7.5-7.5 7.5a7.47 7.47 0 01-3.87-1.07L2.5 17.5l1.07-3.63A7.47 7.47 0 012.5 10c0-4.14 3.36-7.5 7.5-7.5s7.5 3.36 7.5 7.5z" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </span>
                  <div>
                    <div className="vis-memory-title">Discussed QBI eligibility</div>
                    <div className="vis-memory-meta">3 days ago · 2 prior sessions</div>
                  </div>
                </div>
                <div className="vis-memory-alert">
                  <span className="vis-memory-warn">!</span>
                  1 data conflict detected
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Integrations */}
        <div className="integrations-section" data-reveal>
          <div className="integrations-inner">
            <p className="overline">Integrations</p>
            <h2>Connects to the tools<br /><em>you already use</em></h2>
            <p className="integrations-subtitle">One-click connections. No IT department needed.</p>
            <div className="integrations-grid">
              <div className="integration-card">
                <div className="integration-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-8.97 5.7a1.94 1.94 0 01-2.06 0L2 7"/></svg>
                </div>
                <h3>Email</h3>
                <p className="integration-names">Gmail &middot; Outlook</p>
                <p className="integration-desc">Auto-sync client emails and index every conversation for search.</p>
              </div>
              <div className="integration-card">
                <div className="integration-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                </div>
                <h3>Meetings</h3>
                <p className="integration-names">Zoom &middot; Fathom</p>
                <p className="integration-desc">Import recordings and transcripts. Every meeting becomes searchable knowledge.</p>
              </div>
              <div className="integration-card">
                <div className="integration-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 21a9 9 0 100-18 9 9 0 000 18z"/><circle cx="12" cy="12" r="4"/><path d="M4.93 4.93l4.24 4.24M14.83 14.83l4.24 4.24M14.83 9.17l4.24-4.24M4.93 19.07l4.24-4.24"/></svg>
                </div>
                <h3>Browser</h3>
                <p className="integration-names">Chrome Extension</p>
                <p className="integration-desc">Access client intelligence from any tab. Ask questions without leaving your workflow.</p>
              </div>
              <div className="integration-card coming-soon">
                <div className="integration-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                </div>
                <h3>Coming Soon</h3>
                <p className="integration-names">QuickBooks &middot; Calendar Sync</p>
                <p className="integration-desc">Direct accounting data import and calendar-aware deadline management.</p>
                <span className="integration-soon-badge">Coming Q3 2026</span>
              </div>
            </div>
          </div>
        </div>

        {/* Comparison: Meeting Tools vs Callwen */}
        <div className="compare-section" data-reveal>
          <div className="compare-inner">
            <p className="overline">Why Callwen</p>
            <h2>What meeting tools <em>can&apos;t</em> do</h2>
            <p className="compare-subtitle">Meeting tools structure conversations. Callwen delivers the knowledge that makes them count.</p>

            <div className="compare-table-wrap">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th className="compare-th other-col">Meeting &amp; Note Tools</th>
                    <th className="compare-th callwen-col">
                      <span className="callwen-badge">Callwen</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { other: 'Captures meeting transcripts', callwen: 'Analyzes your entire document history \u2014 tax returns, recordings, emails, check-ins' },
                    { other: 'AI summaries of last conversation', callwen: 'AI answers from every document, cross-referenced with financial data' },
                    { other: 'No document intelligence', callwen: '12+ document types auto-classified, 63 financial metrics extracted' },
                    { other: 'No tax compliance features', callwen: 'Built-in IRC \u00a77216 consent tracking with e-signature' },
                    { other: 'Context resets every meeting', callwen: 'Session memory + client journal \u2014 context that compounds over years' },
                    { other: 'No strategy analysis', callwen: 'Tax Strategy Matrix with 15+ strategies, impact tracking, and practice book export' },
                  ].map((row, i) => (
                    <tr key={i} className="compare-row">
                      <td className="compare-td other-col">
                        <svg className="compare-x" viewBox="0 0 16 16" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>
                        {row.other}
                      </td>
                      <td className="compare-td callwen-col">
                        <svg className="compare-check" viewBox="0 0 16 16" fill="none"><path d="M3 8l3.5 3.5L13 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                        {row.callwen}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <a href="#pricing" className="compare-cta">See pricing plans &rarr;</a>
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

        {/* Who It's For */}
        <div className="audience-section" data-reveal>
          <div className="audience-inner">
            <p className="overline">Who it&apos;s for</p>
            <h2>Built for every<br /><em>advisory practice</em></h2>
            <div className="audience-grid">
              <div className="audience-card audience-gold">
                <h3>Solo Practitioners</h3>
                <p>Stop drowning in client files. Callwen gives you back the hours you spend searching for information — so you can spend them advising.</p>
              </div>
              <div className="audience-card audience-teal">
                <h3>Growing Firms</h3>
                <p>Give every team member the same depth of client knowledge. Automated deadlines, shared context, and practice book exports keep everyone aligned.</p>
              </div>
              <div className="audience-card audience-cream">
                <h3>Advisory-Focused Practices</h3>
                <p>Tax strategy tracking, client check-ins, and engagement health scoring — the tools you need to prove and grow your advisory value.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Testimonial Carousel */}
        <div className="testimonials-section" data-reveal>
          <p className="overline">What CPAs are saying</p>
          <h2>What CPAs are saying</h2>
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
                  <li>10 advanced analyses/month</li>
                  <li>Source-cited answers</li>
                  <li>All document types</li>
                </ul>
                <Link href="/sign-up" className="p-btn p-btn-ghost">Start free &rarr;</Link>
              </div>
              <div className="p-card">
                <div className="p-tier">Starter</div>
                <div className="p-price">${starterPrice} <span className="mo">/mo</span></div>
                {annualBilling && <div className="p-billed">billed $948/year</div>}
                <div className="p-desc">Solo practitioners getting organized.</div>
                <ul className="p-list">
                  <li>25 clients</li>
                  <li>Unlimited documents</li>
                  <li>500 AI queries/month</li>
                  <li>50 advanced analyses/month</li>
                  <li>25 premium analyses/month</li>
                  <li>Document comparison</li>
                  <li>Email support</li>
                </ul>
                <Link href="/sign-up" className="p-btn p-btn-ghost">Start 14-day trial</Link>
              </div>
              <div className="p-card featured">
                <div className="p-tier">Professional</div>
                <div className="p-price">${proPrice} <span className="mo">/mo</span></div>
                {annualBilling && <div className="p-billed">billed $1,428/year</div>}
                <div className="p-desc">Growing firms with 10+ clients.</div>
                <ul className="p-list">
                  <li>100 clients</li>
                  <li>Unlimited documents</li>
                  <li>500 AI queries/month</li>
                  <li>100 advanced analyses/month</li>
                  <li>50 premium analyses/month</li>
                  <li>Priority support</li>
                  <li>Client briefs</li>
                </ul>
                <Link href="/sign-up" className="p-btn p-btn-primary">Start 14-day trial</Link>
              </div>
              <div className="p-card">
                <div className="p-tier">Firm</div>
                <div className="p-price">$349 <span className="mo">/mo</span></div>
                <div className="p-desc">3 seats included + $79/mo per seat.</div>
                <ul className="p-list">
                  <li>Unlimited clients &amp; documents</li>
                  <li>1,000 AI queries/month</li>
                  <li>500 advanced analyses/month</li>
                  <li>100 premium analyses/month</li>
                  <li>Multi-user team access</li>
                  <li>Admin controls &amp; audit log</li>
                  <li>Dedicated support</li>
                </ul>
                <Link href="/sign-up" className="p-btn p-btn-ghost">Contact us</Link>
              </div>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <div className="faq-section">
          <p className="overline" data-reveal>FAQ</p>
          <h2 data-reveal>Frequently Asked Questions</h2>
          <div className="faq-filters" data-reveal>
            <button className={`faq-filter${faqFilter === null ? ' active' : ''}`} onClick={() => setFaqFilter(null)}>All</button>
            {faqCategories.map((cat) => (
              <button key={cat.label} className={`faq-filter${faqFilter === cat.label ? ' active' : ''}`} onClick={() => setFaqFilter(cat.label)}>{cat.label}</button>
            ))}
          </div>
          <div className="faq-list" data-reveal>
            {faqCategories.filter((cat) => !faqFilter || cat.label === faqFilter).map((cat) => (
              <div key={cat.label} className="faq-category">
                <div className="faq-category-label">{cat.label}</div>
                {cat.items.map((item, i) => {
                  const key = `${cat.label}-${i}`;
                  return (
                    <div key={key} className={`faq-item${openFaq === key ? ' open' : ''}`}>
                      <button className="faq-q" onClick={() => setOpenFaq(openFaq === key ? null : key)}>
                        <span>{item.q}</span>
                        <span className="faq-icon">{openFaq === key ? '\u00d7' : '+'}</span>
                      </button>
                      {openFaq === key && (
                        <div className="faq-a">{item.a}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        {/* Final CTA */}
        <div className="finale">
          <p className="overline" data-reveal>Ready?</p>
          <h2 data-reveal>Stop searching.<br />Start <em>advising.</em></h2>
          <div className="finale-rule" data-reveal />
          <p className="finale-subtitle" data-reveal>Document intelligence. Tax strategy. Client check-ins. Practice valuation. All in one platform, built by a CPA who got tired of digging through client files.</p>
          <p data-reveal>Free tier includes 5 clients and unlimited documents. No credit card required.</p>
          <Link href="/sign-up" className="cta-btn" data-reveal>
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
.nav-links a { font-size: 0.85rem; font-weight: 400; color: var(--white-dim); text-decoration: none; letter-spacing: 0.04em; transition: color 0.25s; padding: 12px 0; }
.nav-links a:hover { color: var(--white); }
.nav-cta { padding: 12px 24px !important; background: var(--accent) !important; color: var(--bg-deep) !important; font-weight: 500 !important; border-radius: 6px; transition: all 0.25s !important; }
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
.trust-badge-label { font-family: var(--sans); font-size: 0.75rem; font-weight: 400; color: #8a8680; letter-spacing: 0.04em; line-height: 1.35; max-width: 110px; text-align: center; }

/* Metrics strip */
.metrics-row { display: flex; justify-content: center; align-items: center; gap: 0; max-width: 960px; margin: 0 auto; flex-wrap: wrap; }
.metric-item { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 0 40px; }
.metric-number { font-family: var(--serif); font-size: 2.2rem; font-weight: 600; color: var(--accent); line-height: 1; }
.metric-label { font-size: 0.72rem; font-weight: 400; color: var(--white-dim); letter-spacing: 0.06em; text-transform: uppercase; }
.metric-divider { width: 1px; height: 40px; background: rgba(201,148,74,0.15); flex-shrink: 0; }

/* Workflow section */
.workflow-section { padding: 6rem 2rem; border-top: 1px solid rgba(255,255,255,0.03); }
.workflow-inner { max-width: 1000px; margin: 0 auto; text-align: center; }
.workflow-heading { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 3.5rem; color: var(--white); }
.workflow-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 1px; background: rgba(255,255,255,0.03); border-radius: 12px; overflow: hidden; }
.workflow-step { background: rgba(18,21,28,0.85); backdrop-filter: blur(8px); padding: 2.5rem 1.5rem; text-align: center; }
.workflow-num { font-family: var(--serif); font-size: 1.4rem; font-weight: 600; color: var(--accent); opacity: 0.5; margin-bottom: 1rem; }
.workflow-icon { width: 44px; height: 44px; border-radius: 10px; background: var(--teal-dim); display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem; }
.workflow-icon svg { width: 22px; height: 22px; stroke: var(--teal); }
.workflow-step h3 { font-family: var(--sans); font-size: 0.95rem; font-weight: 500; color: var(--white); margin-bottom: 0.6rem; }
.workflow-step p { font-size: 0.8rem; line-height: 1.7; color: var(--white-dim); font-weight: 400; }

/* Feature visual mockups */
.vis-checkin { padding: 1.5rem; display: flex; flex-direction: column; gap: 12px; height: 100%; justify-content: center; }
.vis-checkin-header { font-size: 0.85rem; font-weight: 500; color: var(--white); }
.vis-checkin-rating { display: flex; gap: 2px; }
.vis-star { font-size: 1.2rem; color: rgba(255,255,255,0.12); }
.vis-star.filled { color: #e8b06a; }
.vis-checkin-quote { font-size: 0.78rem; font-style: italic; color: var(--white-dim); line-height: 1.6; }
.vis-checkin-badge { display: inline-block; align-self: flex-start; font-size: 0.65rem; font-weight: 500; padding: 3px 10px; border-radius: 99px; background: var(--teal-dim); color: var(--teal); }

.vis-strategies { padding: 1.2rem; display: flex; flex-direction: column; gap: 0; height: 100%; justify-content: center; }
.vis-strategy-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.04); gap: 8px; }
.vis-strategy-row:last-child { border-bottom: none; }
.vis-strat-name { font-size: 0.78rem; font-weight: 400; color: var(--white); flex: 1; }
.vis-strat-status { font-size: 0.65rem; font-weight: 500; padding: 2px 8px; border-radius: 99px; white-space: nowrap; }
.vis-strat-status.implemented { background: var(--teal-dim); color: var(--teal); }
.vis-strat-status.recommended { background: rgba(201,148,74,0.12); color: var(--accent-light); }
.vis-strat-impact { font-size: 0.72rem; color: var(--white-dim); text-align: right; white-space: nowrap; }

.vis-health { padding: 1.5rem; display: flex; align-items: center; gap: 1.5rem; height: 100%; }
.vis-health-gauge { flex-shrink: 0; }
.vis-health-gauge svg { width: 100px; height: 100px; }
.vis-health-metrics { display: flex; flex-direction: column; gap: 8px; flex: 1; }
.vis-health-row { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
.vis-health-row:last-child { border-bottom: none; }
.vis-health-label { font-size: 0.72rem; color: var(--white-dim); }
.vis-health-val { font-size: 0.78rem; font-weight: 500; color: var(--white); }

.vis-deadlines { padding: 1.5rem; display: flex; flex-direction: column; gap: 0; height: 100%; justify-content: center; }
.vis-deadline-row { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
.vis-deadline-row:last-child { border-bottom: none; }
.vis-deadline-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.vis-deadline-dot.amber { background: #e8b06a; }
.vis-deadline-dot.green { background: #5bb8af; }
.vis-deadline-dot.gray { background: #6a6662; }
.vis-deadline-task { flex: 1; font-size: 0.8rem; color: var(--white); font-weight: 400; }
.vis-deadline-date { font-size: 0.72rem; color: var(--white-dim); white-space: nowrap; }

.vis-memory { padding: 1.5rem; display: flex; flex-direction: column; gap: 12px; height: 100%; justify-content: center; }
.vis-memory-session { display: flex; align-items: flex-start; gap: 10px; }
.vis-memory-icon { flex-shrink: 0; width: 28px; height: 28px; border-radius: 6px; background: var(--teal-dim); display: flex; align-items: center; justify-content: center; }
.vis-memory-icon svg { width: 16px; height: 16px; stroke: var(--teal); }
.vis-memory-title { font-size: 0.82rem; font-weight: 400; color: var(--white); margin-bottom: 2px; }
.vis-memory-meta { font-size: 0.68rem; color: var(--white-faint); }
.vis-memory-alert { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 6px; background: rgba(232,176,106,0.08); border: 1px solid rgba(232,176,106,0.15); font-size: 0.72rem; color: var(--accent-light); }
.vis-memory-warn { width: 18px; height: 18px; border-radius: 50%; background: rgba(232,176,106,0.15); display: flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 700; color: var(--accent-light); flex-shrink: 0; }

/* Integrations section */
.integrations-section { padding: 6rem 2rem; border-top: 1px solid rgba(255,255,255,0.03); }
.integrations-inner { max-width: 1000px; margin: 0 auto; text-align: center; }
.integrations-section .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 1.5rem; }
.integrations-section h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 1rem; line-height: 1.15; }
.integrations-section h2 em { font-style: italic; color: var(--accent-light); }
.integrations-subtitle { font-size: 0.92rem; color: var(--white-dim); margin-bottom: 3rem; font-weight: 400; }
.integrations-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 1px; background: rgba(255,255,255,0.03); border-radius: 12px; overflow: hidden; }
.integration-card { background: rgba(18,21,28,0.85); backdrop-filter: blur(8px); padding: 2.5rem 1.5rem; text-align: center; position: relative; }
.integration-card.coming-soon { opacity: 0.6; }
.integration-icon { width: 44px; height: 44px; border-radius: 10px; background: var(--accent-glow); border: 1px solid rgba(201,148,74,0.12); display: flex; align-items: center; justify-content: center; margin: 0 auto 1.2rem; }
.integration-icon svg { width: 22px; height: 22px; stroke: var(--accent-light); }
.integration-card h3 { font-family: var(--sans); font-size: 0.95rem; font-weight: 500; color: var(--white); margin-bottom: 0.4rem; }
.integration-names { font-size: 0.72rem; color: var(--accent); letter-spacing: 0.06em; margin-bottom: 0.8rem; font-weight: 400; }
.integration-desc { font-size: 0.78rem; line-height: 1.65; color: var(--white-dim); font-weight: 400; }
.integration-soon-badge { display: inline-block; margin-top: 0.8rem; font-size: 0.62rem; font-weight: 500; padding: 3px 10px; border-radius: 99px; background: rgba(255,255,255,0.04); color: var(--white-faint); letter-spacing: 0.06em; }

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
.carousel-dot { width: 44px; height: 44px; border-radius: 50%; border: none; background: transparent; cursor: pointer; transition: all 0.25s; padding: 0; position: relative; }
.carousel-dot::after { content: ''; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 8px; height: 8px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.15); background: transparent; transition: all 0.25s; }
.carousel-dot.active::after { background: var(--accent); border-color: var(--accent); }
.carousel-dot:hover::after { border-color: var(--accent); }
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

/* Comparison: Meeting Tools vs Callwen */
.compare-section { padding: 6rem 2rem; border-top: 1px solid rgba(255,255,255,0.03); }
.compare-inner { max-width: 900px; margin: 0 auto; text-align: center; }
.compare-section .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 1.5rem; }
.compare-section h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 1rem; }
.compare-section h2 em { font-style: italic; color: var(--accent-light); }
.compare-subtitle { font-size: 0.92rem; color: var(--white-dim); margin-bottom: 3rem; font-weight: 400; }
.compare-table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 2.5rem; }
.compare-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; overflow: hidden; background: rgba(18,21,28,0.85); backdrop-filter: blur(8px); }
.compare-th { padding: 1.2rem 1.5rem; font-size: 0.7rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--white-dim); background: rgba(24,28,37,0.9); text-align: left; font-weight: 500; }
.compare-th.callwen-col { text-align: left; }
.callwen-badge { display: inline-block; background: var(--accent); color: var(--bg-deep); font-size: 0.65rem; font-weight: 600; padding: 3px 10px; border-radius: 99px; letter-spacing: 0.1em; }
.compare-row { border-bottom: 1px solid rgba(255,255,255,0.03); }
.compare-td { padding: 1rem 1.5rem; font-size: 0.82rem; line-height: 1.6; vertical-align: top; }
.compare-td.other-col { color: var(--white-faint); font-weight: 400; width: 40%; }
.compare-td.callwen-col { color: var(--white-dim); font-weight: 400; }
.compare-x { width: 14px; height: 14px; color: #e05252; display: inline-block; vertical-align: middle; margin-right: 8px; flex-shrink: 0; }
.compare-check { width: 14px; height: 14px; color: var(--teal); display: inline-block; vertical-align: middle; margin-right: 8px; flex-shrink: 0; }
.compare-cta { display: inline-block; font-size: 0.88rem; font-weight: 500; color: var(--accent); text-decoration: none; transition: color 0.2s; }
.compare-cta:hover { color: var(--accent-light); }

/* Audience / Who It's For */
.audience-section { padding: 6rem 2rem; border-top: 1px solid rgba(255,255,255,0.03); }
.audience-inner { max-width: 1000px; margin: 0 auto; text-align: center; }
.audience-section .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 1.5rem; }
.audience-section h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 3.5rem; line-height: 1.15; }
.audience-section h2 em { font-style: italic; color: var(--accent-light); }
.audience-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 1px; background: rgba(255,255,255,0.03); border-radius: 12px; overflow: hidden; }
.audience-card { background: var(--bg-card); padding: 2.5rem 2rem; text-align: left; transition: all 0.3s ease; }
.audience-card:hover { background: rgba(36,40,52,0.95); }
.audience-card h3 { font-family: var(--sans); font-size: 1rem; font-weight: 500; margin-bottom: 0.8rem; }
.audience-card p { font-size: 0.85rem; line-height: 1.7; color: var(--white-dim); font-weight: 400; }
.audience-gold h3 { color: var(--accent-light); }
.audience-gold { border-top: 2px solid rgba(201,148,74,0.3); }
.audience-teal h3 { color: var(--teal); }
.audience-teal { border-top: 2px solid rgba(91,184,175,0.3); }
.audience-cream h3 { color: var(--white); }
.audience-cream { border-top: 2px solid rgba(240,237,230,0.15); }

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
.toggle-opt { padding: 12px 20px; border-radius: 99px; font-family: var(--sans); font-size: 0.8rem; font-weight: 500; border: none; cursor: pointer; transition: all 0.25s; background: transparent; color: var(--white-dim); }
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
.faq-section h2 { font-family: var(--serif); font-size: clamp(2rem,4vw,3rem); font-weight: 400; margin-bottom: 2rem; }
.faq-filters { display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; margin-bottom: 3rem; }
.faq-filter { padding: 8px 18px; border-radius: 99px; font-family: var(--sans); font-size: 0.78rem; font-weight: 400; border: 1px solid rgba(255,255,255,0.08); background: transparent; color: var(--white-dim); cursor: pointer; transition: all 0.25s; }
.faq-filter:hover { border-color: rgba(201,148,74,0.3); color: var(--white); }
.faq-filter.active { background: var(--accent); color: var(--bg-deep); border-color: var(--accent); font-weight: 500; }
.faq-list { max-width: 740px; margin: 0 auto; text-align: left; }
.faq-category { margin-bottom: 2rem; }
.faq-category-label { font-size: 0.68rem; letter-spacing: 0.25em; text-transform: uppercase; color: var(--accent); font-weight: 500; margin-bottom: 0.5rem; padding-bottom: 0.5rem; border-bottom: 1px solid rgba(201,148,74,0.12); }
.faq-item { border-bottom: 1px solid rgba(255,255,255,0.05); }
.faq-q { display: flex; justify-content: space-between; align-items: center; width: 100%; padding: 1.2rem 0; cursor: pointer; background: none; border: none; font-family: var(--sans); font-size: 0.95rem; font-weight: 400; color: var(--white); transition: color 0.25s; text-align: left; }
.faq-q:hover { color: var(--accent-light); }
.faq-icon { color: var(--accent); font-size: 1.2rem; flex-shrink: 0; margin-left: 1rem; transition: transform 0.3s; }
.faq-a { padding: 0 0 1.5rem; font-size: 0.88rem; line-height: 1.8; color: var(--white-dim); font-weight: 400; }

.finale { min-height: 80vh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 6rem 2rem; }
.finale .overline { font-size: 0.7rem; letter-spacing: 0.35em; text-transform: uppercase; color: var(--accent); margin-bottom: 2rem; }
.finale h2 { font-family: var(--serif); font-size: clamp(2.5rem,6vw,4.5rem); font-weight: 400; line-height: 1.1; margin-bottom: 1.5rem; color: var(--white); }
.finale-rule { width: 50px; height: 1px; background: var(--accent); margin: 0 auto 1.5rem; opacity: 0.6; }
.finale h2 em { font-style: italic; color: var(--accent-light); }
.finale-subtitle { max-width: 560px; margin: 0 auto 1rem; font-size: 1.05rem; line-height: 1.7; color: var(--white-dim); font-weight: 400; }
.finale p { max-width: 480px; margin: 0 auto; font-size: 0.95rem; line-height: 1.7; color: var(--white-faint); font-weight: 400; }
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
.foot-email { font-size: 0.8rem; color: #9a9590; text-decoration: none; transition: color 0.2s; }
.foot-email:hover { color: var(--white-dim); }
.foot-col { display: flex; flex-direction: column; gap: 0.6rem; }
.foot-col h4 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.2em; color: var(--white); margin-bottom: 0.4rem; font-weight: 500; }
.foot-col a { font-size: 0.82rem; color: #9a9590; text-decoration: none; transition: color 0.2s; }
.foot-col a:hover { color: var(--white-dim); }
.foot-soon { font-size: 0.82rem; color: var(--white-faint); opacity: 0.4; cursor: default; }
.foot-bottom { display: flex; align-items: center; justify-content: space-between; padding-top: 2rem; border-top: 1px solid rgba(255,255,255,0.05); }
.foot-copy { font-size: 0.75rem; color: #9a9590; }
.foot-social { display: flex; gap: 1rem; }
.foot-social a { color: #9a9590; transition: color 0.2s; }
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
  .metrics-row { gap: 0; }
  .metric-item { padding: 0 24px; }
  .metric-number { font-size: 1.6rem; }
  .workflow-grid { grid-template-columns: repeat(2,1fr); }
  .integrations-grid { grid-template-columns: repeat(2,1fr); }
  .audience-grid { grid-template-columns: 1fr; }
  .compare-td { font-size: 0.78rem; padding: 0.8rem 1rem; }
  .faq-filters { gap: 6px; }
  .faq-filter { padding: 6px 14px; font-size: 0.72rem; }
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
  .metrics-row { flex-direction: column; gap: 20px; }
  .metric-divider { width: 40px; height: 1px; }
  .workflow-grid { grid-template-columns: 1fr; }
  .integrations-grid { grid-template-columns: 1fr 1fr; }
  .faq-filters { display: none; }
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
