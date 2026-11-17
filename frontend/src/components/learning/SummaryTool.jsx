import { useState } from "react";
import { AlignLeft, Sparkles } from "lucide-react";
import Card from "../ui/Card";
import ToolForm from "./ToolForm";
import { CitationChip, GroundedNote, ResultMeta, ResultNotice, ToolLoading } from "./ResultParts";
import { SUMMARY_LENGTHS, learningApi } from "../../services/learning";
import { getErrorMessage } from "../../services/api";
import "./learning.css";

export default function SummaryTool({ courseId, documents, docsLoading, onOpenDocuments }) {
  const [length, setLength] = useState("medium");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null); // { data, docName }

  const run = async (params) => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await learningApi.summarize(courseId, { ...params, length });
      const doc = documents.find((d) => String(d.id) === params.documentId);
      setResult({ data, docName: doc?.name ?? "" });
    } catch (err) {
      setError(getErrorMessage(err, "Could not generate the summary."));
    } finally {
      setLoading(false);
    }
  };

  const data = result?.data;

  return (
    <div className="lt-tool">
      <ToolForm
        documents={documents}
        docsLoading={docsLoading}
        onOpenDocuments={onOpenDocuments}
        onSubmit={run}
        loading={loading}
        error={error}
        submitLabel="Generate summary"
        submitIcon={Sparkles}
      >
        <div className="field">
          <label>Length</label>
          <div className="seg" role="group" aria-label="Summary length">
            {SUMMARY_LENGTHS.map((l) => (
              <button
                key={l}
                type="button"
                className={length === l ? "on" : ""}
                aria-pressed={length === l}
                onClick={() => setLength(l)}
                disabled={loading}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
      </ToolForm>

      {loading && <ToolLoading label="Generating summary… this can take a moment." />}

      {data && (
        <Card className="anim-fade-up">
          <div className="lt-result-head">
            <div className="lt-result-title">
              <h3><AlignLeft size={16} style={{ verticalAlign: "-2px", marginRight: 6 }} />Summary</h3>
              {result.docName && <span className="lt-result-doc">{result.docName}</span>}
            </div>
            <ResultMeta pageRange={data.pageRange} grounded={data.grounded} partial={data.partial} provider={data.provider} />
          </div>

          <ResultNotice
            partial={data.partial}
            message={data.message}
            partialFallback="Partial result: this summary may not cover the entire selected range."
          />
          <GroundedNote grounded={data.grounded} />

          {data.summary ? (
            <div className="lt-text">{data.summary}</div>
          ) : (
            <div className="lt-text lt-empty-text">The backend returned an empty summary.</div>
          )}

          {data.keyPoints.length > 0 && (
            <>
              <div className="lt-section-title">Key points</div>
              <ul className="lt-points">
                {data.keyPoints.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </>
          )}

          {data.citations.length > 0 && (
            <>
              <div className="lt-section-title">Sources</div>
              <div className="lt-cites">
                {data.citations.map((c, i) => <CitationChip key={`${c.documentId}-${c.page}-${i}`} citation={c} />)}
              </div>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
