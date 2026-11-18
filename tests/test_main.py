"""Tests for QuantumTeleportation-Lab: simulator, protocol, receipt,
dense coding, noisy channels, ledger, classifier, gates."""
import math

import pytest

import main as m


# ---- simulator primitives
def test_hadamard_makes_plus():
    plus = m.apply_1q(m.zero_state(1), m.GATE_H, 0, 1)
    assert abs(plus[0] - 1.0 / m.SQRT2) < 1e-12
    assert abs(plus[1] - 1.0 / m.SQRT2) < 1e-12


def test_cnot_truth_table():
    for ctrl in (0, 1):
        for tgt in (0, 1):
            state = m.zero_state(2)
            if ctrl:
                state = m.apply_1q(state, m.GATE_X, 0, 2)
            if tgt:
                state = m.apply_1q(state, m.GATE_X, 1, 2)
            state = m.apply_cnot(state, 0, 1, 2)
            assert abs(state[ctrl * 2 + (tgt ^ ctrl)] - 1.0) < 1e-12


def test_bell_pair_amplitudes():
    pair = m.bell_pair_state()
    assert abs(pair[0] - 1.0 / m.SQRT2) < 1e-12
    assert abs(pair[3] - 1.0 / m.SQRT2) < 1e-12
    assert abs(pair[1]) < 1e-12 and abs(pair[2]) < 1e-12


def test_input_state_rejects_unnormalised():
    with pytest.raises(ValueError):
        m.input_state(1.0, 1.0)


# ---- ideal teleportation
def test_headline_outcome_probabilities():
    result = m.teleport_statevector(m.HEADLINE_ALPHA, m.HEADLINE_BETA)
    for outcome in result["outcomes"].values():
        assert abs(outcome["probability"] - 0.25) < 1e-12


def test_headline_outcome_fidelities():
    result = m.teleport_statevector(m.HEADLINE_ALPHA, m.HEADLINE_BETA)
    for outcome in result["outcomes"].values():
        assert outcome["fidelity"] > 1.0 - 1e-12


def test_outcome00_needs_no_correction():
    result = m.teleport_statevector(m.HEADLINE_ALPHA, m.HEADLINE_BETA)
    psi = m.input_state(m.HEADLINE_ALPHA, m.HEADLINE_BETA)
    raw = result["outcomes"]["00"]["bob_before_correction"]
    assert all(abs(a - b) < 1e-12 for a, b in zip(raw, psi))


def test_grid_states_all_teleport_perfectly():
    report = m.grid_teleport_report()
    assert report["states_tested"] == 8
    assert report["worst_fidelity"] > 1.0 - 1e-12
    assert report["worst_probability_error_vs_quarter"] < 1e-12


def test_teleport_report_probability_sum():
    report = m.teleport_report()
    assert abs(report["probability_sum"] - 1.0) < 1e-9
    assert report["min_fidelity"] > 1.0 - 1e-9


# ---- no-cloning receipt
def test_alice_original_is_maximally_mixed():
    receipt = m.clone_receipt()
    assert receipt["alice_qubit_is_half_identity_max_dev"] < 1e-12
    assert receipt["alice_both_qubits_max_dev_vs_quarter_identity"] < 1e-12


def test_alice_leftover_overlap_is_half():
    receipt = m.clone_receipt()
    assert abs(receipt["overlap_input_with_alice_leftover"] - 0.5) < 1e-12


def test_bob_has_nothing_before_classical_bits():
    receipt = m.clone_receipt()
    assert receipt["bob_before_classical_bits_max_dev_vs_half_identity"] < 1e-12


def test_receipt_is_input_independent():
    other = m.clone_receipt(0.28, math.sqrt(1.0 - 0.28 ** 2))
    assert other["alice_qubit_is_half_identity_max_dev"] < 1e-12
    assert abs(other["overlap_input_with_alice_leftover"] - 0.5) < 1e-12


# ---- superdense coding
def test_dense_coding_all_messages():
    report = m.dense_report()
    assert report["all_decoded_correctly"]
    for row in report["messages"].values():
        assert abs(row["probability"] - 1.0) < 1e-12


def test_dense_encoded_states_orthonormal():
    report = m.dense_report()
    assert report["encoded_states_orthonormal_margin"] > 1.0 - 1e-12


# ---- noisy channels
def test_noise_zero_strength_is_perfect():
    for channel in ("depolarizing", "dephasing"):
        fid = m.teleport_dm(m.HEADLINE_ALPHA, m.HEADLINE_BETA,
                            channel, 0.0)["fidelity"]
        assert abs(fid - 1.0) < 1e-12


@pytest.mark.parametrize("p", [0.25, 0.5, 0.75, 1.0])
def test_depolarizing_matches_closed_form(p):
    sim = m.teleport_dm(m.HEADLINE_ALPHA, m.HEADLINE_BETA,
                        "depolarizing", p)["fidelity"]
    assert abs(sim - (1.0 - 2.0 * p / 3.0)) < 1e-9


@pytest.mark.parametrize("q", [0.25, 0.5, 1.0])
def test_dephasing_matches_closed_form(q):
    sim = m.teleport_dm(m.HEADLINE_ALPHA, m.HEADLINE_BETA,
                        "dephasing", q)["fidelity"]
    expected = (1.0 - q) + q * (0.36 - 0.64) ** 2
    assert abs(sim - expected) < 1e-9


def test_dephasing_fully_dephased_headline_value():
    fid = m.teleport_dm(m.HEADLINE_ALPHA, m.HEADLINE_BETA,
                        "dephasing", 1.0)["fidelity"]
    assert abs(fid - 0.0784) < 1e-9


def test_dephasing_equatorial_input():
    equi = 1.0 / m.SQRT2
    fid = m.teleport_dm(equi, equi, "dephasing", 0.5)["fidelity"]
    assert abs(fid - 0.5) < 1e-9


def test_depolarizing_fully_noisy_is_half():
    fid = m.teleport_dm(m.HEADLINE_ALPHA, m.HEADLINE_BETA,
                        "depolarizing", 0.75)["fidelity"]
    assert abs(fid - 0.5) < 1e-9


def test_noise_table_monotone():
    table = m.noise_table()
    for channel in ("depolarizing", "dephasing"):
        fids = [table[channel][f"{s / 10.0:.1f}"]["simulated"]
                for s in range(11)]
        assert all(fids[i] >= fids[i + 1] - 1e-12 for i in range(10))


def test_crossings():
    assert abs(m.crossing_strength("depolarizing") - 0.5) < 1e-6
    assert abs(m.crossing_strength("dephasing")
               - m.crossing_analytic("dephasing")) < 1e-6
    assert abs(m.crossing_analytic("dephasing") - 0.361690) < 1e-6


# ---- resource ledger
def test_classical_single_copy_is_two_thirds():
    assert abs(m.classical_estimation_fidelity(1) - 2.0 / 3.0) < 1e-12


def test_classical_copies_for_099():
    assert m.copies_needed(0.99) == 98
    assert abs(m.classical_estimation_fidelity(98) - 0.99) < 1e-12


def test_classical_never_reaches_one():
    assert m.classical_estimation_fidelity(10 ** 6) < 1.0


def test_ledger_quantum_side():
    ledger = m.ledger_report()
    q = ledger["quantum_teleportation"]
    assert q["ebits_consumed"] == 1
    assert q["classical_bits_sent"] == 2
    assert q["fidelity"] == 1.0


# ---- classifier
def test_classifier_scenario_labels():
    scenarios = m.classifier_scenarios()
    assert scenarios["ideal_link"]["label"] == "perfect-protocol"
    assert scenarios["depolarizing_light_p0.25"]["label"] == "beats-classical"
    assert scenarios["depolarizing_threshold_p0.50"]["label"] == "classical-tie"
    assert scenarios["depolarizing_heavy_p0.90"]["label"] == "broken"
    assert scenarios["dephasing_light_q0.20"]["label"] == "beats-classical"
    assert scenarios["dephasing_heavy_q0.90"]["label"] == "broken"


def test_classifier_matches_policy_on_scenarios():
    for row in m.classifier_scenarios().values():
        fid = m.analytic_fidelity(row["channel"], row["noise"])
        assert m.classify_link(row["channel"], row["noise"], fid) == \
            m.policy_label(m.CHANNEL_CODES[row["channel"]], row["noise"], fid)


# ---- gates + seats
def test_hold_gates_14_all_hold():
    assert len(m.HOLD_GATES) == 14
    assert all(v.startswith("HOLD") for v in m.HOLD_GATES.values())


def test_specific_gates_hold():
    assert m.gate("real_message_transmission") == "HOLD"
    assert m.gate("faster_than_light_claim") == "HOLD"
    assert m.gate("state_cloning_claim") == "HOLD"
    assert m.gate("qkd_service_claim") == "HOLD"
    assert m.gate("run_simulation") == "PROCEED"


def test_seats_never_override():
    brains = m.brains_report()
    assert brains["decider"]["can_override_hold"] is False
    assert brains["decider"]["seat"] == "Gemini Argon 4 Extended Thinking"
    assert brains["decider"]["model_id"] == "gemini-argon-4"
    assert brains["advisor"]["can_override_hold"] is False
    assert brains["flow"]["rendered"] is False
    assert brains["flow"]["live"] == 0


def test_checks_all_pass():
    checks = m.run_checks()
    assert all(ok for _, ok in checks)
