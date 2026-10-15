export default function ModulePage({ crumb, title, lead }) {
  return (
    <section className="page">
      <div className="page-head">
        <div>
          <p className="page-kicker">{crumb}</p>
          <h1>{title}</h1>
          <p className="page-lead">{lead}</p>
        </div>
      </div>
      <article className="panel empty-panel">
        <h2>{title}</h2>
        <p>Cet écran est dans la navigation. Son contenu détaillé arrivera avec le module correspondant.</p>
      </article>
    </section>
  );
}
