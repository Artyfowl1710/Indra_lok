import type { ReactNode } from "react";

type StitchPageMastheadProps = {
  section: string;
  title: string;
  description: string;
  meta?: ReactNode;
  actions?: ReactNode;
};

export function StitchPageMasthead({
  section,
  title,
  description,
  meta,
  actions,
}: StitchPageMastheadProps) {
  return (
    <section className="stitch-masthead">
      <div className="stitch-masthead__copy">
        <p className="stitch-eyebrow">INDRA / {section}</p>
        <h2>{title}</h2>
        <p className="stitch-masthead__description">{description}</p>
        {meta ? <div className="stitch-masthead__meta">{meta}</div> : null}
      </div>
      {actions ? <div className="stitch-masthead__actions">{actions}</div> : null}
    </section>
  );
}
