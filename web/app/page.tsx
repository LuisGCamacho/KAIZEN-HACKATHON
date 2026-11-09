import { EvolutionView } from "../components/views/evolution-view";

export default function EvolucionPage() {
  return <EvolutionView
    reports={{ status: "empty" }}
    artifacts={{ status: "empty" }}
    progress={{ status: "empty" }}
  />;
}
