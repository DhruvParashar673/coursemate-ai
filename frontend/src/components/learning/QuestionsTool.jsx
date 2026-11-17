import { useState } from "react";
import { ListChecks, Sparkles } from "lucide-react";
import Card from "../ui/Card";
import ToolForm from "./ToolForm";
import { CitationChip, GroundedNote, ResultMeta, ResultNotice, ToolLoading } from "./ResultParts";
import { MAX_QUESTIONS, MIN_QUESTIONS, learningApi } from "../../services/learning";
import { getErrorMessage } from "../../services/api";
import "./learning.css";

const typeLabel = (t) => t.replace(/[_-]+/g, " ");

export default function QuestionsTool({ courseId, documents, docsLoading, onOpenDocuments }) {
  const [count, setCount] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null); // { data, docName }

  const run = async (params) => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await learningApi.importantQuestions(courseId, { ...params, count });
      const doc = documents.find((d) => String(d.id) === params.documentId);
      setResult({ data, docName: doc?.name ?? "" });
    } catch (err) {
      setError(getErrorMessage(err, "Could not generate important questions."));
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
        submitLabel="Generate questions"
        submitIcon={Sparkles}
      >
        <div className="field">
          <label htmlFor="lt-count">Number of questions</label>
          <div className="lt-range">
            <input
              id="lt-count"
              type="range"
              min={MIN_QUESTIONS}
              max={MAX_QUESTIONS}
              step={1}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              disabled={loading}
            />
            <span className="lt-range-value">{count}</span>
          </div>
        </div>
      </ToolForm>

      {loading && <ToolLoading label="Finding the most important questions…" />}

      {data && (
        <Card className="anim-fade-up">
          <div className="lt-result-head">
            <div className="lt-result-title">
              <h3><ListChecks size={16} style={{ verticalAlign: "-2px", marginRight: 6 }} />Important questions</h3>
              {result.docName && <span className="lt-result-doc">{result.docName}</span>}
            </div>
            <ResultMeta pageRange={data.pageRange} grounded={data.grounded} partial={data.partial} provider={data.provider} />
          </div>

          <ResultNotice
            partial={data.partial}
            message={data.message}
            partialFallback="Partial result: fewer questions than requested may have been generated."
          />
          <GroundedNote grounded={data.grounded} />

          {data.questions.length === 0 ? (
            <div className="lt-text lt-empty-text">No questions were returned for this selection.</div>
          ) : (
            <ol className="lt-questions">
              {data.questions.map((q, i) => (
                <li key={i} className="lt-q">
                  <div className="lt-q-num" aria-hidden="true" />
                  <div className="lt-q-body">
                    <div className="lt-q-text">{q.question}</div>
                    {q.why && <div className="lt-q-why"><strong>Why it matters:</strong> {q.why}</div>}
                    {(q.type || q.citation) && (
                      <div className="lt-q-foot">
                        {q.type && <span className="badge" style={{ textTransform: "capitalize" }}>{typeLabel(q.type)}</span>}
                        {q.citation && <CitationChip citation={q.citation} />}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}
    </div>
  );
}
