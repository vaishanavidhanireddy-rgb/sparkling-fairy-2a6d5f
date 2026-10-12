"""Tiny Grover search experiment using Qiskit's local Aer simulator.

Candidate terms and their importance scores are prepared classically. A phase
oracle marks the highest-scoring candidates; Grover amplitude amplification then
searches that small candidate set on a simulated quantum circuit. This is an
educational demonstration, not a clinical model or a speedup over classical code.
"""
import math

from qiskit import QuantumCircuit
from qiskit.circuit.library import GroverOperator
from qiskit_aer import AerSimulator

from ai.report_comparison import compare_reports
from quantum.feature_selection import rank_shared_features

SHOTS = 1024
MAX_CANDIDATES = 8


def _phase_oracle(marked_indices, qubit_count):
    """Flip phase for candidate indices, using q0 as the least-significant bit."""
    oracle = QuantumCircuit(qubit_count)
    for index in marked_indices:
        bits = format(index, f"0{qubit_count}b")
        zero_qubits = [qubit for qubit, bit in enumerate(reversed(bits)) if bit == "0"]
        for qubit in zero_qubits:
            oracle.x(qubit)
        if qubit_count == 1:
            oracle.z(0)
        else:
            target = qubit_count - 1
            oracle.h(target)
            oracle.mcx(list(range(target)), target)
            oracle.h(target)
        for qubit in reversed(zero_qubits):
            oracle.x(qubit)
    return oracle


def analyze(first, second):
    result = compare_reports(first, second)
    candidates = rank_shared_features(first, second, limit=MAX_CANDIDATES)
    if not candidates:
        result.update(
            selected_features=[],
            method="No shared terms were found, so no quantum search was run.",
            quantum={"ran": False},
        )
        return result

    # Oracle construction uses classical term overlap; the circuit searches the
    # resulting toy candidate set and returns measured candidate indices.
    candidate_count = len(candidates)
    qubit_count = max(1, math.ceil(math.log2(candidate_count)))
    state_count = 2 ** qubit_count
    marked_count = min(candidate_count, max(1, round(math.sqrt(candidate_count))))
    marked_indices = list(range(marked_count))
    iterations = max(0, round((math.pi / 4) * math.sqrt(state_count / marked_count) - 0.5))

    oracle = _phase_oracle(marked_indices, qubit_count)
    circuit = QuantumCircuit(qubit_count)
    circuit.h(range(qubit_count))
    grover = GroverOperator(oracle)
    for _ in range(iterations):
        circuit.compose(grover, inplace=True)
    circuit.measure_all()

    simulator = AerSimulator()
    counts = simulator.run(circuit, shots=SHOTS, seed_simulator=17).result().get_counts()
    valid_counts = {}
    for bitstring, count in counts.items():
        candidate_index = int(bitstring.replace(" ", ""), 2)
        if candidate_index < candidate_count:
            valid_counts[candidate_index] = count

    selected_indices = sorted(
        valid_counts,
        key=lambda index: (-valid_counts[index], index),
    )[:marked_count]
    selected = [candidates[index]["term"] for index in selected_indices]
    measurements = [
        {"term": candidates[index]["term"], "count": valid_counts[index],
         "probability": round(valid_counts[index] / SHOTS, 3)}
        for index in selected_indices
    ]
    result["selected_features"] = selected
    result["method"] = (
        "Qiskit Aer Grover search simulation. Candidate terms and the oracle scores "
        "come from classical word overlap; no medical meaning is inferred."
    )
    result["quantum"] = {
        "ran": True,
        "simulator": "Qiskit AerSimulator (local classical computer)",
        "algorithm": "Grover amplitude amplification",
        "qubits": qubit_count,
        "iterations": iterations,
        "shots": SHOTS,
        "candidate_count": candidate_count,
        "marked_count": marked_count,
        "measurements": measurements,
        "circuit": str(circuit.draw(output="text")),
    }
    return result
