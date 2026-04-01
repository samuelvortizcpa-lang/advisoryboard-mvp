const { createCanvas } = require('canvas');
const fs = require('fs');
const path = require('path');

const sizes = [16, 32, 48, 128];

sizes.forEach(size => {
  const canvas = createCanvas(size, size);
  const ctx = canvas.getContext('2d');

  const radius = size * 0.2;
  const hasBorder = size >= 48;

  // Rounded rectangle helper
  function roundedRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  // Faint gold border (48 and 128 only)
  if (hasBorder) {
    roundedRect(0, 0, size, size, radius);
    ctx.fillStyle = 'rgba(201,148,74,0.3)';
    ctx.fill();
  }

  // Dark background
  const inset = hasBorder ? 1 : 0;
  roundedRect(inset, inset, size - inset * 2, size - inset * 2, radius - inset);
  ctx.fillStyle = '#12151c';
  ctx.fill();

  // Gold "C" in Cormorant Garamond style (serif fallback)
  ctx.fillStyle = '#c9944a';
  ctx.font = `bold ${Math.floor(size * 0.65)}px "Cormorant Garamond", Georgia, serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('C', size / 2, size / 2 + size * 0.03);

  const buffer = canvas.toBuffer('image/png');
  const filePath = path.join(__dirname, 'src', 'assets', `icon-${size}.png`);
  fs.writeFileSync(filePath, buffer);
  console.log(`Created ${filePath}`);
});
