/**
 * ==============================================================================
 * DOUALAFLOW — map.js (Refonte Google Maps / Apple Maps style)
 * ==============================================================================
 * Carte Leaflet immersive avec :
 * - Tuiles sombres premium (Stadia Alidade Smooth Dark)
 * - Routes colorées épaissies avec glow pour les saturations
 * - Popups style Google Maps (arrondis, ombre, bien structurés)
 * - Animation fluide des véhicules
 * - Bouton "reset view"
 * ==============================================================================
 */

// Configuration carte
const MAP_CONFIG = {
  center:  [4.0580, 9.7080],  // Centre de Douala
  zoom:    13,
  minZoom: 11,
  maxZoom: 18,
};

// Tuiles multiples avec fallback automatique
const TILE_OPTIONS = [
  {
    url:   "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attr:  '&copy; <a href="https://openstreetmap.org">OSM</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    name:  "CartoDB Dark",
  },
  {
    url:   "https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png",
    attr:  '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a>',
    name:  "Stadia Dark",
  },
  {
    url:   "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr:  '&copy; <a href="https://openstreetmap.org">OpenStreetMap</a> contributors',
    name:  "OSM",
  },
];

// Axes routiers
const AXES_CONFIG = {
  ndokoti: {
    label: "Ndokoti", zone: "Carrefour Central — Zone très dense",
    coords: [[4.0511,9.7085],[4.0530,9.7095],[4.0550,9.7100],[4.0570,9.7110],[4.0590,9.7105],[4.0610,9.7095]],
  },
  bonaberi: {
    label: "Bonabéri", zone: "Pont sur le Wouri — Axe inter-rives",
    coords: [[4.0731,9.6821],[4.0720,9.6850],[4.0710,9.6880],[4.0695,9.6910],[4.0680,9.6940],[4.0660,9.6960]],
  },
  bassa: {
    label: "Bassa", zone: "Zone Industrielle — Trafic lourd",
    coords: [[4.0234,9.7412],[4.0250,9.7430],[4.0265,9.7450],[4.0280,9.7465],[4.0295,9.7480],[4.0310,9.7490]],
  },
  akwa: {
    label: "Akwa", zone: "Centre-Ville & Affaires",
    coords: [[4.0487,9.7012],[4.0500,9.7030],[4.0515,9.7048],[4.0528,9.7063],[4.0540,9.7078],[4.0555,9.7090]],
  },
  makepe: {
    label: "Makepe", zone: "Zone Résidentielle Nord",
    coords: [[4.0812,9.7234],[4.0825,9.7250],[4.0838,9.7265],[4.0850,9.7280],[4.0862,9.7295],[4.0875,9.7305]],
  },
  logbessou: {
    label: "Logbessou", zone: "Périphérie Nord — Accès autoroute",
    coords: [[4.1021,9.7156],[4.1005,9.7170],[4.0990,9.7185],[4.0975,9.7198],[4.0960,9.7212],[4.0945,9.7225]],
  },
};

// ============================================================================
// MODULE CARTE
// ============================================================================
const DoualaMape = (() => {

  let map           = null;
  let polylines     = {};
  let glowLines     = {};    // Lignes de halo sous les routes
  let nodeMarkers   = {};
  let vehicleMarkers = {};
  let axisData      = {};

  // Couleurs trafic alignées sur le nouveau design
  const getColor = (c) => c > 70 ? '#ff3b30' : c > 55 ? '#ff9500' : c > 40 ? '#ffcc00' : '#34c759';
  const getStatus = (c) => c > 70 ? 'SATURÉ' : c > 40 ? 'RALENTI' : 'FLUIDE';

  // HTML du popup style Google Maps
  const buildPopup = (name, data) => {
    const c    = data?.congestion ?? 0;
    const spd  = data?.speed_kmh  ?? 0;
    const st   = data?.status     ?? '—';
    const zone = AXES_CONFIG[name]?.zone ?? '';
    const col  = getColor(c);

    return `
      <div class="axis-popup-inner">
        <div class="popup-axis-name" style="color:${col}">
          ● ${AXES_CONFIG[name]?.label ?? name}
        </div>
        <div class="popup-axis-zone">${zone}</div>
        <div class="popup-stat">
          <span class="popup-stat-key">Congestion</span>
          <span class="popup-stat-val" style="color:${col}">${c.toFixed(1)}%</span>
        </div>
        <div class="popup-stat">
          <span class="popup-stat-key">Vitesse moyenne</span>
          <span class="popup-stat-val">${spd.toFixed(1)} km/h</span>
        </div>
        <div class="popup-stat">
          <span class="popup-stat-key">Statut</span>
          <span class="popup-stat-val" style="color:${col}">${st}</span>
        </div>
        <div class="popup-stat">
          <span class="popup-stat-key">Véhicules</span>
          <span class="popup-stat-val">${data?.vehicle_count ?? '—'}</span>
        </div>
      </div>`;
  };

  // ============================================================================
  // INITIALISATION
  // ============================================================================
  const init = () => {
    map = L.map('map', {
      center:      MAP_CONFIG.center,
      zoom:        MAP_CONFIG.zoom,
      minZoom:     MAP_CONFIG.minZoom,
      maxZoom:     MAP_CONFIG.maxZoom,
      zoomControl: false,
    });

    // Zoom en bas à droite
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // Tuiles officielles OpenStreetMap (100% gratuit, pas de clé API, jamais bloqué)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 18
    }).addTo(map);

    // Dessiner les axes
    Object.entries(AXES_CONFIG).forEach(([name, cfg]) => {
      // Halo (glow) sous la route — effet "lumineux"
      const glow = L.polyline(cfg.coords, {
        color:   '#ffffff',
        weight:  14,
        opacity: 0.03,
        lineCap: 'round',
      }).addTo(map);
      glowLines[name] = glow;

      // Route principale
      const poly = L.polyline(cfg.coords, {
        color:     '#34c759',
        weight:    5,
        opacity:   0.95,
        lineCap:   'round',
        lineJoin:  'round',
        className: `axis-line axis-${name}`,
      });

      poly.bindPopup(() => buildPopup(name, axisData[name]), {
        className: 'dark-popup',
        maxWidth:  240,
      });

      poly.on('mouseover', function() { this.setStyle({ weight: 8, opacity: 1 }); });
      poly.on('mouseout',  function() { this.setStyle({ weight: 5, opacity: 0.95 }); });

      poly.addTo(map);
      polylines[name] = poly;

      // Marqueur nœud central
      const midIdx = Math.floor(cfg.coords.length / 2);
      const node   = L.circleMarker(cfg.coords[midIdx], {
        radius:      7,
        fillColor:   '#34c759',
        color:       '#34c759',
        weight:      2,
        opacity:     0.9,
        fillOpacity: 0.4,
        className:   `node-${name}`,
      });

      node.bindTooltip(cfg.label, {
        permanent:  true,
        direction:  'top',
        offset:     [0, -10],
        className:  'axis-tooltip',
      });

      node.bindPopup(() => buildPopup(name, axisData[name]), { className: 'dark-popup', maxWidth: 240 });
      node.addTo(map);
      nodeMarkers[name] = node;
    });

    console.log('[DoualaMape] Carte initialisée ✓');
  };

  // ============================================================================
  // MISE À JOUR DES AXES (couleurs temps réel)
  // ============================================================================
  const updateAxes = (data) => {
    if (!data?.axes) return;
    axisData = data.axes;

    Object.entries(data.axes).forEach(([name, info]) => {
      const poly = polylines[name];
      const glow = glowLines[name];
      const node = nodeMarkers[name];
      if (!poly) return;

      const color  = info.color ?? getColor(info.congestion);
      const weight = info.status === 'SATURÉ' ? 7 : 5;

      poly.setStyle({ color, weight, opacity: 0.95 });

      // Glow plus intense si saturé
      if (glow) {
        const glowOpacity = info.status === 'SATURÉ' ? 0.08 : 0.03;
        glow.setStyle({ color, opacity: glowOpacity, weight: weight + 10 });
      }

      // Mettre à jour le nœud central
      if (node) {
        node.setStyle({ fillColor: color, color });
      }
    });
  };

  // ============================================================================
  // ANIMATION DES VÉHICULES
  // ============================================================================
  const updateVehicles = (vehicles) => {
    if (!map || !vehicles) return;

    const curIds = new Set(Object.keys(vehicleMarkers));
    const newIds = new Set(vehicles.map(v => v.id));

    // Supprimer les anciens
    curIds.forEach(id => {
      if (!newIds.has(id)) {
        map.removeLayer(vehicleMarkers[id]);
        delete vehicleMarkers[id];
      }
    });

    // Ajouter / déplacer
    vehicles.forEach(v => {
      if (!v.lat || !v.lon) return;

      if (vehicleMarkers[v.id]) {
        vehicleMarkers[v.id].setLatLng([v.lat, v.lon]);
        vehicleMarkers[v.id].setStyle({ fillColor: v.color, color: v.color });
      } else {
        const mk = L.circleMarker([v.lat, v.lon], {
          radius:      4,
          fillColor:   v.color,
          color:       v.color,
          weight:      1.5,
          opacity:     0.9,
          fillOpacity: 1,
        });
        mk.bindTooltip(`${v.label} · ${(v.speed ?? 0).toFixed(0)} km/h`, {
          direction: 'top',
          offset:    [0, -5],
        });
        mk.addTo(map);
        vehicleMarkers[v.id] = mk;
      }
    });

    // Compteur
    const el = document.getElementById('vehicle-count');
    if (el) el.textContent = vehicles.length;
  };

  // ============================================================================
  // CENTRER SUR UN AXE
  // ============================================================================
  const focusAxis = (name) => {
    const cfg  = AXES_CONFIG[name];
    const poly = polylines[name];
    if (!cfg || !poly) return;

    const midIdx = Math.floor(cfg.coords.length / 2);
    map.flyTo(cfg.coords[midIdx], 15, { duration: 0.8, easeLinearity: 0.4 });
    setTimeout(() => poly.openPopup(), 900);
  };

  // ============================================================================
  // RÉINITIALISER LA VUE
  // ============================================================================
  const resetView = () => {
    map.flyTo(MAP_CONFIG.center, MAP_CONFIG.zoom, { duration: 0.8 });
  };

  return { init, updateAxes, updateVehicles, focusAxis, resetView };

})();

// Initialiser au chargement
document.addEventListener('DOMContentLoaded', () => {
  DoualaMape.init();
  console.log('[DoualaFlow] Carte Leaflet prête ✓');
});
