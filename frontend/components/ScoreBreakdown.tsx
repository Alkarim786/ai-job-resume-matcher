import type { Score, SkillMatch } from "@/lib/api";

const PARTS: { key: keyof Score; label: string; weight: number }[] = [
  { key: "semantic", label: "Semantic", weight: 0.5 },
  { key: "skills", label: "Skills", weight: 0.3 },
  { key: "experience", label: "Experience", weight: 0.1 },
  { key: "title", label: "Title", weight: 0.1 },
];

export const pct = (x: number) => `${Math.round(x * 100)}%`;

export function ScoreBreakdown({ score, skills }: { score: Score; skills?: SkillMatch }) {
  return (
    <div className="score" data-testid="score">
      <div className="total">
        <strong aria-label="match score">{pct(score.total)}</strong> match
      </div>
      {PARTS.map((p) => (
        <div className="bar" key={p.key} title={`${p.label}: ${pct(score[p.key])} × weight ${p.weight}`}>
          <span className="bar-label">{p.label} <em>×{p.weight}</em></span>
          <span className="bar-track"><span className="bar-fill" style={{ width: pct(score[p.key]) }} /></span>
          <span className="bar-val">{pct(score[p.key])}</span>
        </div>
      ))}
      {skills && (
        <div className="chips">
          {skills.matched_must.map((s) => <span key={"m" + s} className="chip ok">✓ {s}</span>)}
          {skills.missing_must.map((s) => <span key={"x" + s} className="chip bad">✗ {s} (required)</span>)}
          {skills.matched_nice.map((s) => <span key={"n" + s} className="chip soft">✓ {s}</span>)}
        </div>
      )}
    </div>
  );
}
