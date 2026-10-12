export default function AuthLayout({ children }) {
  return (
    <div className="auth">
      <section className="auth-hero">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22">
              <rect x="3" y="10" width="3" height="8" rx="1" fill="currentColor" />
              <rect x="10.5" y="6" width="3" height="12" rx="1" fill="currentColor" />
              <rect x="18" y="3" width="3" height="15" rx="1" fill="currentColor" />
            </svg>
          </span>
          <span className="brand-name">TradeLab</span>
        </div>

        <div className="hero-copy">
          <p className="hero-kicker">Simulateur de salle de marché</p>
          <h1>
            Apprenez. Simulez.
            <br />
            <span>Progressez.</span>
          </h1>
          <p className="hero-lead">
            Pratiquez le trading en toute sécurité avec des données réalistes, des analyses
            professionnelles et un capital 100 % virtuel.
          </p>
        </div>

        <div className="chart-card">
          <div className="chart-top">
            <span>EUR / USD</span>
            <strong>
              1,0842 <em>+0,42 %</em>
            </strong>
          </div>
          <svg className="chart" viewBox="0 0 560 210" role="img" aria-label="Graphique illustratif EUR/USD">
            <defs>
              <linearGradient id="lineFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3d8bfd" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#3d8bfd" stopOpacity="0" />
              </linearGradient>
            </defs>
            {[40, 80, 120, 160].map((y) => (
              <line key={y} x1="16" y1={y} x2="544" y2={y} stroke="rgba(255,255,255,0.06)" />
            ))}
            {[
              [48, 118, 78, "down"],
              [92, 96, 70, "up"],
              [136, 128, 64, "down"],
              [180, 104, 58, "up"],
              [224, 90, 72, "up"],
              [268, 112, 48, "down"],
              [312, 78, 66, "up"],
              [356, 88, 40, "up"],
              [400, 70, 52, "down"],
              [444, 60, 46, "up"],
              [488, 52, 38, "up"],
            ].map(([x, y, h, side]) => (
              <g key={x}>
                <line
                  x1={x + 8}
                  y1={y - 14}
                  x2={x + 8}
                  y2={y + h + 14}
                  stroke={side === "up" ? "#3dd68c" : "#ff5d73"}
                  strokeWidth="2"
                />
                <rect
                  x={x}
                  y={y}
                  width="16"
                  height={h}
                  rx="2"
                  fill={side === "up" ? "#3dd68c" : "#ff5d73"}
                />
              </g>
            ))}
            <path
              d="M24 150 C 90 132, 140 118, 190 124 S 280 86, 340 92 S 450 48, 536 58 L 536 190 L 24 190 Z"
              fill="url(#lineFill)"
            />
            <path
              d="M24 150 C 90 132, 140 118, 190 124 S 280 86, 340 92 S 450 48, 536 58"
              fill="none"
              stroke="#5aa6ff"
              strokeWidth="3"
            />
          </svg>
          <p className="profit">
            Profit virtuel
            <strong>+ 2 840,50 TND</strong>
          </p>
        </div>

        <div className="hero-foot">
          <span>Environnement sécurisé</span>
          <span>Données en temps réel</span>
        </div>
      </section>
      <section className="auth-panel">{children}</section>
    </div>
  );
}
