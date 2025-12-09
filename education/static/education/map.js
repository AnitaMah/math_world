document.addEventListener("DOMContentLoaded", () => {
  const svg = document.getElementById("mapSvg");
  const mapWrap = document.querySelector(".map-wrap") || document.body;
  const radius = 40;

  // SVG groups
  const linksGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const nodesGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
  svg.appendChild(linksGroup);
  svg.appendChild(nodesGroup);

  // Tooltip
  const tooltip = document.createElement("div");
  tooltip.className = "map-tooltip";
  mapWrap.appendChild(tooltip);

  // Back button
  const controls = document.querySelector(".map-controls");
  if (controls) {
    const backBtn = document.createElement("button");
    backBtn.className = "button back-btn";
    backBtn.textContent = "← Back";
    backBtn.addEventListener("click", (e) => {
      e.preventDefault();
      if (document.referrer) window.history.back();
    });
    controls.insertBefore(backBtn, controls.firstChild);
  }

  // Handle image background
  const img = document.getElementById("mapImg");
  if (img) {
    mapWrap.classList.add("has-image");
    const setupOverlay = () => {
      const iw = img.naturalWidth || img.width;
      const ih = img.naturalHeight || img.height;
      if (iw && ih) {
        svg.setAttribute("viewBox", `0 0 ${iw} ${ih}`);
        svg.style.height = img.clientHeight + "px";
        svg.style.width = "100%";
      }
    };
    if (img.complete) setupOverlay();
    else img.addEventListener("load", setupOverlay);
  }

  // Draw nodes
  map.nodes.forEach((node) => {
    if (typeof node.x !== "number" || typeof node.y !== "number") return;

    const x = node.x;
    const y = node.y;

    // Circle
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", x);
    circle.setAttribute("cy", y);
    circle.setAttribute("r", radius);
    circle.setAttribute("fill", node.color || "#66bb6a");
    circle.setAttribute("stroke", "#fff");
    circle.setAttribute("stroke-width", "2");
    circle.classList.add("node-circle");
    circle.style.cursor = node.url ? "pointer" : "default";

    circle.addEventListener("mouseenter", (ev) => {
      circle.setAttribute("r", radius * 1.08);
      tooltip.style.display = "block";
      tooltip.textContent = node.name || "";
    });
    circle.addEventListener("mousemove", (ev) => {
      tooltip.style.left = ev.pageX + 12 + "px";
      tooltip.style.top = ev.pageY + 12 + "px";
    });
    circle.addEventListener("mouseleave", () => {
      circle.setAttribute("r", radius);
      tooltip.style.display = "none";
    });
    circle.addEventListener("click", () => {
      if (node.url) window.location.href = node.url;
    });

    nodesGroup.appendChild(circle);

    // Label
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", x);
    label.setAttribute("y", y + radius + 18);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("font-size", "14");
    label.setAttribute("fill", "#fff");
    label.classList.add("node-label");
    label.textContent = node.name || "";
    label.style.cursor = node.url ? "pointer" : "default";
    label.addEventListener("click", () => {
      if (node.url) window.location.href = node.url;
    });

    nodesGroup.appendChild(label);
  });

  // Reset progress (stub)
  const resetBtn = document.getElementById("resetProgressBtn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      alert("Прогрес скинуто!");
    });
  }
});