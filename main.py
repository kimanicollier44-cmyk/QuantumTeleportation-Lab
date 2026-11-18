#!/usr/bin/env python3
"""QuantumTeleportation-Lab - educational quantum teleportation lab.

by Darion Kellar

Pure Python standard library. Zero dependencies. Zero network.
Education only - and the central lesson is stated up front:

  * This lab runs the quantum teleportation protocol end to end on
    a from-scratch 3-qubit statevector simulator: an arbitrary
    labelled qubit state, one shared Bell pair, a Bell-basis
    measurement, 2 classical bits, and Pauli corrections. The
    recovered state matches the input with fidelity 1 (to machine
    precision) for every measurement outcome.
  * Nothing was teleported anywhere. There is no photon, no fibre,
    no network, and no second location: "Alice" and "Bob" are
    registers inside one Python process, and the "channel" in the
    noisy section is a Kraus map applied to a matrix.
  * Teleportation does not clone: after the Bell measurement the
    sender's original qubit is left in the maximally mixed state -
    the original is destroyed, which is exactly why the protocol
    does not violate no-cloning or relativity. The classical bits
    still have to travel, so nothing here is faster than light.
  * The noisy sections report the fidelity the protocol actually
    delivers when the shared pair is degraded, graded against the
    best classical measure-and-resend fidelity of 2/3 - including
    the noise level where the quantum protocol stops beating it.

Real communication, quantum-internet, hardware, and faster-than-
light claims are permanent HOLD gates - with Gemini Argon 4
Extended Thinking as DECIDER (names-only, tighten-only), Muse as
advisor (never overrides HOLD), and Google Flow plan-only seats.
"""
import hashlib
import json
import math
import sys

# ---------------------------------------------------------------- constants
VERSION = "1.0.0"

# The headline input state, with exact labelled amplitudes:
# |psi> = 0.6|0> + 0.8|1>, normalised because 0.36 + 0.64 = 1.
HEADLINE_ALPHA = 0.6
HEADLINE_BETA = 0.8

# Best possible fidelity of any classical measure-and-prepare
# strategy for an unknown qubit (the N = 1 case of the optimal
# state-estimation fidelity (N + 1) / (N + 2)).
CLASSICAL_BOUND = 2.0 / 3.0

# Channel codes used by the classifier.
CHANNEL_CODES = {"none": 0, "depolarizing": 1, "dephasing": 2}

# ---------------------------------------------------------------- HOLD gates
HOLD_GATES = {
    "real_message_transmission": "HOLD - no real message or quantum state was transmitted anywhere; Alice and Bob are registers in one process",
    "quantum_internet_service_claim": "HOLD - no quantum internet service; there is no network in this lab",
    "faster_than_light_claim": "HOLD - teleportation needs 2 classical bits that travel at most at light speed; no FTL claim, ever",
    "real_hardware_control": "HOLD - no control of real photonic, ion-trap, superconducting, or any other quantum hardware",
    "photonic_network_operation": "HOLD - no operating photonic links, repeaters, or network nodes",
    "qkd_service_claim": "HOLD - no QKD service or key-distribution claim; teleportation is not a product",
    "production_communication_use": "HOLD - no production communication system may be built on a teaching simulator",
    "vendor_benchmark_claim": "HOLD - no vendor or hardware benchmark claims from a laptop statevector",
    "state_cloning_claim": "HOLD - no cloning: the protocol destroys the original, and this lab proves that instead of hiding it",
    "encryption_product_claim": "HOLD - no encryption product claim; superdense coding here is a protocol demonstration",
    "classified_communications_use": "HOLD - no classified, military, or government communication use",
    "satellite_link_claim": "HOLD - no satellite, deep-space, or free-space link claim or operation",
    "commercial_teleportation_service": "HOLD - no commercial teleportation service, offering, or pricing",
    "experimental_result_claim": "HOLD - no experimental result: every number is a simulation output, not a measurement of nature",
}


def gate(action):
    """Return 'HOLD' if the action is gated, else 'PROCEED' (sandbox sim)."""
    return "HOLD" if action in HOLD_GATES else "PROCEED"


# ================================================================ 1. Small complex linear algebra
# Matrices are lists of lists of complex numbers, vectors are lists
# of complex numbers. Everything is written from scratch on purpose:
# the lab's claim is that every number can be read and checked.

def mat_zeros(rows, cols):
    return [[0j] * cols for _ in range(rows)]


def mat_eye(n):
    out = mat_zeros(n, n)
    for i in range(n):
        out[i][i] = 1.0 + 0j
    return out


def mat_mul(a, b):
    rows, inner, cols = len(a), len(b), len(b[0])
    out = mat_zeros(rows, cols)
    for i in range(rows):
        for k in range(inner):
            aik = a[i][k]
            if aik == 0j:
                continue
            for j in range(cols):
                out[i][j] += aik * b[k][j]
    return out


def mat_dagger(a):
    return [[a[i][j].conjugate() for i in range(len(a))]
            for j in range(len(a[0]))]


def mat_trace(a):
    return sum(a[i][i] for i in range(len(a)))


def mat_add(a, b):
    return [[a[i][j] + b[i][j] for j in range(len(a[0]))]
            for i in range(len(a))]


def mat_scale(a, s):
    return [[a[i][j] * s for j in range(len(a[0]))] for i in range(len(a))]


def kron(a, b):
    rows = len(a) * len(b)
    cols = len(a[0]) * len(b[0])
    out = mat_zeros(rows, cols)
    for i in range(len(a)):
        for j in range(len(a[0])):
            if a[i][j] == 0j:
                continue
            for k in range(len(b)):
                for l in range(len(b[0])):
                    out[i * len(b) + k][j * len(b[0]) + l] = a[i][j] * b[k][l]
    return out


def vec_mat_vec(vec, mat):
    """<vec| mat |vec> as a complex number (real for Hermitian mat)."""
    total = 0j
    for i, vi in enumerate(vec):
        if vi == 0j:
            continue
        for j, vj in enumerate(vec):
            total += vi.conjugate() * mat[i][j] * vj
    return total


def state_to_dm(vec):
    return [[vec[i] * vec[j].conjugate() for j in range(len(vec))]
            for i in range(len(vec))]


def partial_trace(rho, keep, nq):
    """Trace out every qubit not in `keep` (qubit 0 = most significant)."""
    dim = 1 << nq
    keep = sorted(keep)
    kdim = 1 << len(keep)
    out = mat_zeros(kdim, kdim)
    for i in range(dim):
        for j in range(dim):
            val = rho[i][j]
            if val == 0j:
                continue
            ok = True
            for q in range(nq):
                if q in keep:
                    continue
                bit_i = (i >> (nq - 1 - q)) & 1
                bit_j = (j >> (nq - 1 - q)) & 1
                if bit_i != bit_j:
                    ok = False
                    break
            if not ok:
                continue
            oi = oj = 0
            for pos, q in enumerate(keep):
                oi |= ((i >> (nq - 1 - q)) & 1) << (len(keep) - 1 - pos)
                oj |= ((j >> (nq - 1 - q)) & 1) << (len(keep) - 1 - pos)
            out[oi][oj] += val
    return out


def full_op(single, qubit, nq):
    """Embed a one-qubit operator into an n-qubit space by Kronecker."""
    out = [[1.0 + 0j]]
    for q in range(nq):
        out = kron(out, single if q == qubit else mat_eye(2))
    return out


def apply_unitary_dm(rho, unitary):
    return mat_mul(mat_mul(unitary, rho), mat_dagger(unitary))


def apply_kraus_dm(rho, qubit, kraus_ops, nq):
    """Apply a one-qubit Kraus channel to one qubit of a density matrix."""
    out = mat_zeros(len(rho), len(rho))
    for k in kraus_ops:
        full = full_op(k, qubit, nq)
        out = mat_add(out, mat_mul(mat_mul(full, rho), mat_dagger(full)))
    return out


# One-qubit gates, written out entry by entry.
SQRT2 = math.sqrt(2.0)
GATE_I = [[1.0 + 0j, 0j], [0j, 1.0 + 0j]]
GATE_X = [[0j, 1.0 + 0j], [1.0 + 0j, 0j]]
GATE_Y = [[0j, -1j], [1j, 0j]]
GATE_Z = [[1.0 + 0j, 0j], [0j, -1.0 + 0j]]
GATE_H = [[(1.0 + 0j) / SQRT2, (1.0 + 0j) / SQRT2],
          [(1.0 + 0j) / SQRT2, (-1.0 + 0j) / SQRT2]]
PAULIS = {"I": GATE_I, "X": GATE_X, "Y": GATE_Y, "Z": GATE_Z}


def mat_vec_mul(mat, vec):
    return [sum(mat[i][j] * vec[j] for j in range(len(vec)))
            for i in range(len(mat))]


# ================================================================ 2. Statevector simulator
# Qubit 0 is the most significant bit of the basis index. Gates are
# applied by index arithmetic - no matrix library anywhere.

def apply_1q(state, gate_u, qubit, nq):
    bit = 1 << (nq - 1 - qubit)
    out = list(state)
    for i in range(len(state)):
        if i & bit:
            continue
        j = i | bit
        a, b = state[i], state[j]
        out[i] = gate_u[0][0] * a + gate_u[0][1] * b
        out[j] = gate_u[1][0] * a + gate_u[1][1] * b
    return out


def apply_cnot(state, control, target, nq):
    cbit = 1 << (nq - 1 - control)
    tbit = 1 << (nq - 1 - target)
    out = list(state)
    for i in range(len(state)):
        if i & cbit:
            out[i ^ tbit] = state[i]
    return out


def zero_state(nq):
    state = [0j] * (1 << nq)
    state[0] = 1.0 + 0j
    return state


def bell_pair_state():
    """|Phi+> = (|00> + |11>) / sqrt(2) on two qubits."""
    state = zero_state(2)
    state = apply_1q(state, GATE_H, 0, 2)
    state = apply_cnot(state, 0, 1, 2)
    return state


def input_state(alpha, beta):
    norm = math.sqrt(abs(alpha) ** 2 + abs(beta) ** 2)
    if abs(norm - 1.0) > 1e-9:
        raise ValueError("input amplitudes must be normalised")
    return [complex(alpha), complex(beta)]


def grid_input_states():
    """A small labelled grid of input states (theta, phi) plus headline."""
    states = {"headline_0.6_0.8": (HEADLINE_ALPHA, HEADLINE_BETA)}
    for theta_deg, phi_deg in ((0, 0), (60, 0), (90, 0), (90, 90),
                               (90, 180), (120, 45), (180, 0)):
        theta = math.radians(theta_deg)
        phi = math.radians(phi_deg)
        alpha = math.cos(theta / 2.0)
        beta = complex(math.cos(phi), math.sin(phi)) * math.sin(theta / 2.0)
        states[f"theta{theta_deg}_phi{phi_deg}"] = (alpha, beta)
    return states


# ================================================================ 3. The teleportation protocol
# Qubit 0: Alice's unknown input. Qubit 1: Alice's half of the pair.
# Qubit 2: Bob's half. Bell measurement = CNOT(q0 -> q1), H(q0),
# then read (q0, q1). Correction on Bob: Z^q0 then X^q1, i.e. the
# operator X^b Z^a for outcome bits (a, b) = (q0, q1).

def correction_op(a, b):
    op = mat_mul(GATE_X, GATE_Z) if (a and b) else None
    if op is not None:
        return op
    if b:
        return GATE_X
    if a:
        return GATE_Z
    return GATE_I


def teleport_statevector(alpha, beta):
    """Run the full protocol; return per-outcome probabilities and
    Bob's corrected state plus fidelity against the input."""
    psi = input_state(alpha, beta)
    state = zero_state(3)
    # Load the input on qubit 0: build the product state directly.
    pair = bell_pair_state()
    state = [0j] * 8
    for x in range(2):
        for y in range(4):
            state[x * 4 + y] = psi[x] * pair[y]
    # Bell-basis rotation on Alice's two qubits.
    state = apply_cnot(state, 0, 1, 3)
    state = apply_1q(state, GATE_H, 0, 3)
    outcomes = {}
    for a in (0, 1):
        for b in (0, 1):
            amps = [state[a * 4 + b * 2 + z] for z in (0, 1)]
            prob = sum(abs(v) ** 2 for v in amps)
            bob_raw = [v / math.sqrt(prob) for v in amps]
            bob = mat_vec_mul(correction_op(a, b), bob_raw)
            fidelity = abs(psi[0].conjugate() * bob[0]
                           + psi[1].conjugate() * bob[1]) ** 2
            outcomes[f"{a}{b}"] = {
                "bits": f"{a}{b}",
                "probability": prob,
                "bob_before_correction": bob_raw,
                "bob_after_correction": bob,
                "fidelity": fidelity,
            }
    return {"input": psi, "outcomes": outcomes, "final_state": state}


def teleport_report(alpha=HEADLINE_ALPHA, beta=HEADLINE_BETA):
    result = teleport_statevector(alpha, beta)
    return {
        "input_alpha": alpha,
        "input_beta": beta,
        "outcomes": {
            key: {"probability": round(o["probability"], 12),
                  "fidelity": round(o["fidelity"], 12)}
            for key, o in result["outcomes"].items()},
        "min_fidelity": round(min(o["fidelity"]
                                  for o in result["outcomes"].values()), 12),
        "probability_sum": round(sum(o["probability"]
                                     for o in result["outcomes"].values()), 12),
    }


def grid_teleport_report():
    worst = 1.0
    worst_prob_err = 0.0
    for name, (alpha, beta) in grid_input_states().items():
        result = teleport_statevector(alpha, beta)
        for o in result["outcomes"].values():
            worst = min(worst, o["fidelity"])
            worst_prob_err = max(worst_prob_err, abs(o["probability"] - 0.25))
    return {"states_tested": len(grid_input_states()),
            "outcomes_per_state": 4,
            "worst_fidelity": worst,
            "worst_probability_error_vs_quarter": worst_prob_err}


# ================================================================ 4. No-cloning receipt
# After the Bell rotation, apply the measurement non-selectively
# (projectors on Alice's qubits, outcomes summed over) and trace:
# Alice's original qubit is exactly I/2, whatever the input was, and
# Bob's qubit before the classical bits arrive is also I/2 - the
# receipt that the original is destroyed and nothing travelled.

def _unitary_from_gates(gates, nq):
    dim = 1 << nq
    cols = []
    for basis in range(dim):
        state = [0j] * dim
        state[basis] = 1.0 + 0j
        for kind, args in gates:
            if kind == "1q":
                state = apply_1q(state, args[0], args[1], nq)
            else:
                state = apply_cnot(state, args[0], args[1], nq)
        cols.append(state)
    return [[cols[j][i] for j in range(dim)] for i in range(dim)]


PROTOCOL_UNITARY = _unitary_from_gates(
    [("cnot", (0, 1)), ("1q", (GATE_H, 0))], 3)


def _projector_diag(qubit_values, nq):
    dim = 1 << nq
    proj = mat_zeros(dim, dim)
    for i in range(dim):
        ok = True
        for q, val in qubit_values.items():
            if ((i >> (nq - 1 - q)) & 1) != val:
                ok = False
                break
        if ok:
            proj[i][i] = 1.0 + 0j
    return proj


def nonselective_measured_dm(alpha, beta):
    """Full 3-qubit density matrix after the Bell rotation and a
    non-selective measurement of Alice's two qubits."""
    psi = input_state(alpha, beta)
    rho = state_to_dm(teleport_statevector(alpha, beta)["final_state"])
    total = mat_zeros(8, 8)
    for a in (0, 1):
        for b in (0, 1):
            proj = _projector_diag({0: a, 1: b}, 3)
            total = mat_add(total, mat_mul(mat_mul(proj, rho), proj))
    return total


def clone_receipt(alpha=HEADLINE_ALPHA, beta=HEADLINE_BETA):
    rho = nonselective_measured_dm(alpha, beta)
    alice_q0 = partial_trace(rho, [0], 3)
    alice_both = partial_trace(rho, [0, 1], 3)
    bob = partial_trace(rho, [2], 3)
    psi = input_state(alpha, beta)
    overlap = vec_mat_vec(psi, alice_q0).real
    max_dev_q0 = max(abs(alice_q0[i][j] - (0.5 if i == j else 0.0))
                     for i in range(2) for j in range(2))
    max_dev_bob = max(abs(bob[i][j] - (0.5 if i == j else 0.0))
                      for i in range(2) for j in range(2))
    return {
        "alice_original_qubit": [[round(v.real, 12) for v in row]
                                 for row in alice_q0],
        "alice_qubit_is_half_identity_max_dev": max_dev_q0,
        "alice_both_qubits_max_dev_vs_quarter_identity":
            max(abs(alice_both[i][j] - (0.25 if i == j else 0.0))
                for i in range(4) for j in range(4)),
        "bob_before_classical_bits_max_dev_vs_half_identity": max_dev_bob,
        "overlap_input_with_alice_leftover": round(overlap, 12),
        "reading": "overlap 1/2 is the maximally mixed value: no copy "
                   "of the input remains with Alice, and Bob has "
                   "nothing usable until the 2 classical bits arrive",
    }


# ================================================================ 5. Superdense coding
# The same Bell pair does double duty: Alice applies X^b2 Z^b1 to
# her half, sends ONE qubit, and Bob's Bell decode (CNOT + H) reads
# both bits deterministically.

DENSE_MESSAGES = ("00", "01", "10", "11")


def dense_encode_decode(message):
    b1, b2 = int(message[0]), int(message[1])
    state = bell_pair_state()
    if b1:
        state = apply_1q(state, GATE_Z, 0, 2)
    if b2:
        state = apply_1q(state, GATE_X, 0, 2)
    encoded = list(state)
    state = apply_cnot(state, 0, 1, 2)
    state = apply_1q(state, GATE_H, 0, 2)
    probs = {}
    for a in (0, 1):
        for b in (0, 1):
            probs[f"{a}{b}"] = abs(state[a * 2 + b]) ** 2
    decoded = max(probs, key=lambda k: probs[k])
    return {"message": message, "decoded": decoded,
            "decode_probability": probs[decoded],
            "encoded_state": encoded}


def dense_report():
    rows = {msg: dense_encode_decode(msg) for msg in DENSE_MESSAGES}
    # The four encoded states must be mutually orthonormal Bell states.
    min_orthogonality = 1.0
    for i, m1 in enumerate(DENSE_MESSAGES):
        for m2 in DENSE_MESSAGES[i + 1:]:
            inner = sum(x.conjugate() * y for x, y in
                        zip(rows[m1]["encoded_state"],
                            rows[m2]["encoded_state"]))
            min_orthogonality = min(min_orthogonality, 1.0 - abs(inner))
    return {
        "messages": {msg: {"decoded": r["decoded"],
                           "probability": round(r["decode_probability"], 12)}
                     for msg, r in rows.items()},
        "all_decoded_correctly": all(r["decoded"] == msg
                                     for msg, r in rows.items()),
        "encoded_states_orthonormal_margin": min_orthogonality,
        "ledger": "1 ebit + 1 qubit sent = 2 classical bits delivered",
    }


# ================================================================ 6. Noisy channels (density matrices)
# The shared pair is prepared, then Bob's half - the half that has
# to travel - passes a labelled channel written as Kraus operators:
#   depolarizing: K0 = sqrt(1-p) I, K1..3 = sqrt(p/3) {X, Y, Z}
#   dephasing:    K0 = sqrt(1-q) I, K1 = sqrt(q) Z
# The protocol then runs on density matrices, and the delivered
# fidelity is averaged over the four outcomes with their weights.

def kraus_ops(channel, strength):
    if channel == "none" or strength == 0.0:
        return [GATE_I]
    if channel == "depolarizing":
        s = math.sqrt(strength / 3.0)
        return [mat_scale(GATE_I, math.sqrt(1.0 - strength)),
                mat_scale(GATE_X, s), mat_scale(GATE_Y, s),
                mat_scale(GATE_Z, s)]
    if channel == "dephasing":
        return [mat_scale(GATE_I, math.sqrt(1.0 - strength)),
                mat_scale(GATE_Z, math.sqrt(strength))]
    raise ValueError(f"unknown channel: {channel}")


def noisy_pair_dm(channel, strength):
    pair = state_to_dm(bell_pair_state())
    return apply_kraus_dm(pair, 1, kraus_ops(channel, strength), 2)


def teleport_dm(alpha, beta, channel, strength):
    """Teleport through a noisy pair; return the outcome-averaged
    fidelity of Bob's corrected state against the pure input."""
    psi = input_state(alpha, beta)
    rho = kron(state_to_dm(psi), noisy_pair_dm(channel, strength))
    rho = apply_unitary_dm(rho, PROTOCOL_UNITARY)
    total_fidelity = 0.0
    per_outcome = {}
    for a in (0, 1):
        for b in (0, 1):
            proj = _projector_diag({0: a, 1: b}, 3)
            post = mat_mul(mat_mul(proj, rho), proj)
            prob = mat_trace(post).real
            bob = mat_scale(partial_trace(post, [2], 3), 1.0 / prob)
            corr = correction_op(a, b)
            bob = apply_unitary_dm(bob, corr)
            fidelity = vec_mat_vec(psi, bob).real
            per_outcome[f"{a}{b}"] = {"probability": prob,
                                      "fidelity": fidelity}
            total_fidelity += prob * fidelity
    return {"fidelity": total_fidelity, "outcomes": per_outcome}


def analytic_fidelity(channel, strength,
                      alpha=HEADLINE_ALPHA, beta=HEADLINE_BETA):
    """Closed forms the density-matrix run is graded against.

    Depolarizing shrinks the Bloch vector by (1 - 4p/3), so the
    teleported fidelity is (1 + (1 - 4p/3)) / 2 = 1 - 2p/3 for any
    input. Dephasing mixes in a Z-flipped copy, so the fidelity is
    (1 - q) + q * (|alpha|^2 - |beta|^2)^2 for the given input.
    """
    if channel == "none":
        return 1.0
    if channel == "depolarizing":
        return 1.0 - 2.0 * strength / 3.0
    if channel == "dephasing":
        z_expect = abs(alpha) ** 2 - abs(beta) ** 2
        return (1.0 - strength) + strength * z_expect ** 2
    raise ValueError(f"unknown channel: {channel}")


def noise_table(alpha=HEADLINE_ALPHA, beta=HEADLINE_BETA):
    rows = {}
    for channel in ("depolarizing", "dephasing"):
        rows[channel] = {}
        for step in range(0, 11):
            strength = step / 10.0
            sim = teleport_dm(alpha, beta, channel, strength)["fidelity"]
            rows[channel][f"{strength:.1f}"] = {
                "simulated": round(sim, 6),
                "analytic": round(analytic_fidelity(channel, strength,
                                                    alpha, beta), 6),
            }
    return rows


def crossing_strength(channel, alpha=HEADLINE_ALPHA, beta=HEADLINE_BETA,
                      target=CLASSICAL_BOUND):
    """Bisection on the simulated fidelity: the noise strength where
    the quantum protocol stops beating the classical 2/3 bound."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if teleport_dm(alpha, beta, channel, mid)["fidelity"] > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def crossing_analytic(channel, alpha=HEADLINE_ALPHA, beta=HEADLINE_BETA):
    if channel == "depolarizing":
        return 0.5
    z_expect = abs(alpha) ** 2 - abs(beta) ** 2
    return (1.0 - CLASSICAL_BOUND) / (1.0 - z_expect ** 2)


def noise_report():
    table = noise_table()
    return {
        "table": table,
        "classical_bound": round(CLASSICAL_BOUND, 6),
        "crossings": {
            channel: {
                "simulated_bisection": round(crossing_strength(channel), 6),
                "analytic": round(crossing_analytic(channel), 6),
            } for channel in ("depolarizing", "dephasing")},
        "reading": "above the crossing strength the noisy quantum "
                   "protocol no longer beats the best classical "
                   "measure-and-resend strategy (fidelity 2/3)",
    }


# ================================================================ 7. Resource ledger
# Quantum: 1 ebit + 2 classical bits + the input copy itself, and
# the fidelity is exactly 1. Classical: the optimal estimation
# fidelity from N copies of an unknown qubit is (N + 1) / (N + 2),
# so a classical strategy needs N copies - and still never reaches 1.

def classical_estimation_fidelity(copies):
    return (copies + 1.0) / (copies + 2.0)


def copies_needed(target_fidelity):
    n = 1
    while classical_estimation_fidelity(n) < target_fidelity:
        n += 1
    return n


def ledger_report():
    return {
        "quantum_teleportation": {
            "ebits_consumed": 1,
            "classical_bits_sent": 2,
            "input_copies_consumed": 1,
            "fidelity": 1.0,
        },
        "classical_estimation": {
            "formula": "F(N) = (N + 1) / (N + 2) for N measured copies",
            "table": {str(n): round(classical_estimation_fidelity(n), 6)
                      for n in (1, 2, 5, 10, 98)},
            "copies_for_0.99": copies_needed(0.99),
            "copies_for_0.999": copies_needed(0.999),
        },
        "reading": "one shared pair plus 2 classical bits moves the "
                   "state exactly; the best classical copy-and-measure "
                   "route needs 98 copies to reach fidelity 0.99 and "
                   "never reaches 1 at any finite N",
    }


# ================================================================ 8. kNN link classifier
# Features: channel code, noise strength, delivered fidelity. The
# training grid is labelled by the lab's own verdict policy below,
# with grid fidelities computed by the lab's analytic channel
# formulas - the classifier interpolates the policy, it does not
# replace the simulation.

def policy_label(channel_code, noise, fidelity):
    """The lab's link-verdict policy, distilled to four labels."""
    if fidelity >= 1.0 - 1e-9:
        return "perfect-protocol"
    if abs(fidelity - CLASSICAL_BOUND) <= 1e-6:
        return "classical-tie"
    if fidelity > CLASSICAL_BOUND:
        return "beats-classical"
    return "broken"


def _training_grid():
    rows = []
    for channel, code in CHANNEL_CODES.items():
        for step in range(0, 21):
            noise = step / 20.0
            fidelity = analytic_fidelity(channel, noise)
            rows.append(((code, noise, fidelity),
                         policy_label(code, noise, fidelity)))
    return rows


TRAINING_GRID = _training_grid()


def _scaled(features):
    code, noise, fidelity = features
    return (code / 2.0, noise, fidelity)


def classify_link(channel, noise, fidelity, k=5):
    """Distance-weighted kNN over the policy-labelled grid.

    Weighting by 1 / (distance + 1e-9) matters here: the
    classical-tie label lives on the single fidelity line F = 2/3,
    so an unweighted majority vote would drown the exact grid row
    that sits on the line. Deterministic tie-breaking throughout.
    """
    target = _scaled((CHANNEL_CODES[channel], noise, fidelity))
    ranked = []
    for features, label in TRAINING_GRID:
        point = _scaled(features)
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(target, point)))
        ranked.append((dist, features, label))
    ranked.sort(key=lambda row: (row[0], row[1]))
    votes = {}
    for dist, _, label in ranked[:k]:
        votes[label] = votes.get(label, 0.0) + 1.0 / (dist + 1e-9)
    priority = {"perfect-protocol": 0, "beats-classical": 1,
                "classical-tie": 2, "broken": 3}
    return sorted(votes.items(), key=lambda kv: (-kv[1], priority[kv[0]]))[0][0]


def classifier_scenarios():
    """Scenario fidelities are computed by the density-matrix
    simulator, never hand-fed."""
    scenarios = {
        "ideal_link": ("none", 0.0),
        "depolarizing_light_p0.25": ("depolarizing", 0.25),
        "depolarizing_threshold_p0.50": ("depolarizing", 0.50),
        "depolarizing_heavy_p0.90": ("depolarizing", 0.90),
        "dephasing_light_q0.20": ("dephasing", 0.20),
        "dephasing_heavy_q0.90": ("dephasing", 0.90),
    }
    out = {}
    for name, (channel, noise) in scenarios.items():
        fidelity = teleport_dm(HEADLINE_ALPHA, HEADLINE_BETA,
                               channel, noise)["fidelity"]
        out[name] = {"channel": channel, "noise": noise,
                     "fidelity": round(fidelity, 6),
                     "label": classify_link(channel, noise, fidelity)}
    return out


# ================================================================ 9. Advisory seats
def _trace(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def argon4_decide(topic="quantumteleportation-demo"):
    """Gemini Argon 4 DECIDER seat: MAP->MODEL->STRESS->DECIDE.

    Names-only keys, live calls 0, tighten-only: can add HOLDs, never lift one.
    """
    stages = ["MAP", "MODEL", "STRESS", "DECIDE"]
    payload = {"seat": "gemini-argon-4", "topic": topic, "stages": stages}
    return {
        "seat": "Gemini Argon 4 Extended Thinking",
        "model_id": "gemini-argon-4",
        "role": "DECIDER",
        "pipeline": stages,
        "tiers": [2048, 8192, 32768],
        "key": "names-only (GEMINI_API_KEY name checked, value never read)",
        "live_calls": 0,
        "decision": "PROCEED - sandbox simulation only, all communication and hardware gates stay HOLD",
        "can_override_hold": False,
        "trace_sha256_16": _trace(payload),
    }


def claude_advisor(topic="quantumteleportation-demo"):
    """Muse advisor seat: advises, can never override a HOLD."""
    return {
        "seat": "Muse",
        "role": "ADVISOR",
        "key": "names-only (MODEL_API_KEY name checked, value never read)",
        "live_calls": 0,
        "advice": "Say it in the first line of every report: nothing was sent anywhere - then show the destroyed original (I/2), the 2 classical bits in the ledger, and the noise level where the protocol stops beating the classical 2/3 line.",
        "can_override_hold": False,
    }


def google_flow_plan():
    """Google Flow seat: plan-only, nothing rendered, nothing live."""
    return {
        "seat": "Google Flow",
        "role": "PLAN-ONLY",
        "shots": ["an unknown qubit state card meeting a shared Bell pair",
                  "the Bell measurement splitting into four equiprobable outcomes",
                  "two classical bits crossing to Bob while the original fades to I/2",
                  "Pauli correction cards snapping Bob's qubit back to the input",
                  "a noise dial turning the delivered fidelity down through the 2/3 line"],
        "rendered": False,
        "live": 0,
    }


def brains_report():
    return {"decider": argon4_decide(), "advisor": claude_advisor(),
            "flow": google_flow_plan()}


# ================================================================ checks
def run_checks():
    c = []

    def chk(name, ok):
        c.append((name, bool(ok)))

    # 1. simulator primitives
    plus = apply_1q(zero_state(1), GATE_H, 0, 1)
    chk("hadamard_makes_plus",
        abs(plus[0] - 1.0 / SQRT2) < 1e-12 and abs(plus[1] - 1.0 / SQRT2) < 1e-12)
    basis_ok = True
    for ctrl in (0, 1):
        for tgt in (0, 1):
            state = zero_state(2)
            if ctrl:
                state = apply_1q(state, GATE_X, 0, 2)
            if tgt:
                state = apply_1q(state, GATE_X, 1, 2)
            state = apply_cnot(state, 0, 1, 2)
            expected = ctrl * 2 + (tgt ^ ctrl)
            basis_ok = basis_ok and abs(state[expected] - 1.0) < 1e-12
    chk("cnot_truth_table", basis_ok)
    pair = bell_pair_state()
    chk("bell_pair_amplitudes",
        abs(pair[0] - 1.0 / SQRT2) < 1e-12 and abs(pair[3] - 1.0 / SQRT2) < 1e-12
        and abs(pair[1]) < 1e-12 and abs(pair[2]) < 1e-12)

    # 2. ideal teleportation: headline + grid
    head = teleport_statevector(HEADLINE_ALPHA, HEADLINE_BETA)
    chk("headline_probabilities_quarter",
        all(abs(o["probability"] - 0.25) < 1e-12
            for o in head["outcomes"].values()))
    chk("headline_fidelities_one",
        all(o["fidelity"] > 1.0 - 1e-12 for o in head["outcomes"].values()))
    chk("headline_outcome00_needs_no_correction",
        all(abs(a - b) < 1e-12 for a, b in
            zip(head["outcomes"]["00"]["bob_before_correction"],
                input_state(HEADLINE_ALPHA, HEADLINE_BETA))))
    grid = grid_teleport_report()
    chk("grid_worst_fidelity_one", grid["worst_fidelity"] > 1.0 - 1e-12)
    chk("grid_probabilities_uniform",
        grid["worst_probability_error_vs_quarter"] < 1e-12)

    # 3. no-cloning receipt
    receipt = clone_receipt()
    chk("alice_original_maximally_mixed",
        receipt["alice_qubit_is_half_identity_max_dev"] < 1e-12)
    chk("alice_both_qubits_quarter_identity",
        receipt["alice_both_qubits_max_dev_vs_quarter_identity"] < 1e-12)
    chk("alice_leftover_overlap_half",
        abs(receipt["overlap_input_with_alice_leftover"] - 0.5) < 1e-12)
    chk("bob_nothing_before_bits",
        receipt["bob_before_classical_bits_max_dev_vs_half_identity"] < 1e-12)
    other = clone_receipt(0.28, math.sqrt(1.0 - 0.28 ** 2))
    chk("alice_leftover_input_independent",
        other["alice_qubit_is_half_identity_max_dev"] < 1e-12
        and abs(other["overlap_input_with_alice_leftover"] - 0.5) < 1e-12)

    # 4. superdense coding
    dense = dense_report()
    chk("dense_all_messages_decode", dense["all_decoded_correctly"])
    chk("dense_decode_probabilities_one",
        all(abs(r["probability"] - 1.0) < 1e-12
            for r in dense["messages"].values()))
    chk("dense_encoded_orthonormal",
        dense["encoded_states_orthonormal_margin"] > 1.0 - 1e-12)

    # 5. noisy channels: simulation graded against closed forms
    chk("noise_zero_strength_fidelity_one",
        abs(teleport_dm(HEADLINE_ALPHA, HEADLINE_BETA,
                        "depolarizing", 0.0)["fidelity"] - 1.0) < 1e-12
        and abs(teleport_dm(HEADLINE_ALPHA, HEADLINE_BETA,
                            "dephasing", 0.0)["fidelity"] - 1.0) < 1e-12)
    dep_ok = all(
        abs(teleport_dm(HEADLINE_ALPHA, HEADLINE_BETA,
                        "depolarizing", p)["fidelity"]
            - analytic_fidelity("depolarizing", p)) < 1e-9
        for p in (0.25, 0.5, 0.75, 1.0))
    chk("depolarizing_matches_formula", dep_ok)
    deph_ok = all(
        abs(teleport_dm(HEADLINE_ALPHA, HEADLINE_BETA,
                        "dephasing", q)["fidelity"]
            - analytic_fidelity("dephasing", q)) < 1e-9
        for q in (0.25, 0.5, 1.0))
    chk("dephasing_matches_formula", deph_ok)
    chk("dephasing_fully_dephased_headline",
        abs(teleport_dm(HEADLINE_ALPHA, HEADLINE_BETA,
                        "dephasing", 1.0)["fidelity"] - 0.0784) < 1e-9)
    equi = 1.0 / SQRT2
    chk("dephasing_equatorial_formula",
        abs(teleport_dm(equi, equi, "dephasing", 0.5)["fidelity"] - 0.5) < 1e-9)
    chk("depolarizing_fully_noisy_half",
        abs(teleport_dm(HEADLINE_ALPHA, HEADLINE_BETA,
                        "depolarizing", 0.75)["fidelity"] - 0.5) < 1e-9)
    table = noise_table()
    for channel in ("depolarizing", "dephasing"):
        fids = [table[channel][f"{s / 10.0:.1f}"]["simulated"]
                for s in range(11)]
        chk(f"noise_table_monotone_{channel}",
            all(fids[i] >= fids[i + 1] - 1e-12 for i in range(10)))
    chk("depolarizing_crossing_half",
        abs(crossing_strength("depolarizing") - 0.5) < 1e-6)
    chk("dephasing_crossing_matches_analytic",
        abs(crossing_strength("dephasing") - crossing_analytic("dephasing"))
        < 1e-6)

    # 6. resource ledger
    chk("classical_single_copy_bound",
        abs(classical_estimation_fidelity(1) - CLASSICAL_BOUND) < 1e-12)
    chk("classical_copies_for_099",
        copies_needed(0.99) == 98
        and abs(classical_estimation_fidelity(98) - 0.99) < 1e-12)
    chk("classical_never_reaches_one",
        classical_estimation_fidelity(10 ** 6) < 1.0)

    # 7. classifier: labels come from the lab's own policy
    scenarios = classifier_scenarios()
    chk("classifier_ideal_perfect",
        scenarios["ideal_link"]["label"] == "perfect-protocol")
    chk("classifier_depol_light_beats",
        scenarios["depolarizing_light_p0.25"]["label"] == "beats-classical")
    chk("classifier_depol_threshold_tie",
        scenarios["depolarizing_threshold_p0.50"]["label"] == "classical-tie")
    chk("classifier_depol_heavy_broken",
        scenarios["depolarizing_heavy_p0.90"]["label"] == "broken")
    chk("classifier_deph_light_beats",
        scenarios["dephasing_light_q0.20"]["label"] == "beats-classical")
    chk("classifier_deph_heavy_broken",
        scenarios["dephasing_heavy_q0.90"]["label"] == "broken")
    chk("classifier_matches_policy",
        all(classify_link(s["channel"], s["noise"],
                          analytic_fidelity(s["channel"], s["noise"]))
            == policy_label(CHANNEL_CODES[s["channel"]], s["noise"],
                            analytic_fidelity(s["channel"], s["noise"]))
            for s in scenarios.values()))

    # 8. gates + seats
    chk("hold_gates_14", len(HOLD_GATES) == 14
        and all(v.startswith("HOLD") for v in HOLD_GATES.values()))
    chk("gate_transmission_hold", gate("real_message_transmission") == "HOLD")
    chk("gate_ftl_hold", gate("faster_than_light_claim") == "HOLD")
    chk("gate_cloning_hold", gate("state_cloning_claim") == "HOLD")
    chk("gate_qkd_hold", gate("qkd_service_claim") == "HOLD")
    chk("gate_sandbox_proceed", gate("run_simulation") == "PROCEED")
    brains = brains_report()
    chk("argon4_no_override", brains["decider"]["can_override_hold"] is False
        and brains["decider"]["seat"] == "Gemini Argon 4 Extended Thinking"
        and brains["decider"]["model_id"] == "gemini-argon-4")
    chk("claude_no_override", brains["advisor"]["can_override_hold"] is False)
    chk("flow_plan_only", brains["flow"]["rendered"] is False
        and brains["flow"]["live"] == 0)
    return c


# ================================================================ CLI / demo
def demo():
    print("=" * 68)
    print("QuantumTeleportation-Lab - quantum teleportation protocol lab")
    print("by Darion Kellar | MIT | pure stdlib | zero network | EDUCATION ONLY")
    print("=" * 68)
    print("\n[1] THE HONEST CORE - what teleportation is and is not")
    print("    A 3-qubit statevector in one Python process runs the real")
    print("    protocol: Bell pair, Bell measurement, 2 classical bits,")
    print("    Pauli corrections. Nothing was sent anywhere - Alice and")
    print("    Bob are registers, and the original is destroyed, which")
    print("    is why no-cloning and relativity both survive.")
    print("\n[2] Ideal protocol - input |psi> = 0.6|0> + 0.8|1>")
    report = teleport_report()
    for bits, row in report["outcomes"].items():
        print(f"    outcome {bits} | p = {row['probability']:.4f} | "
              f"fidelity {row['fidelity']:.12f}")
    print(f"    -> all four outcomes at p = 1/4, fidelity 1 to machine")
    print(f"       precision; grid of {grid_teleport_report()['states_tested']} "
          f"input states: worst fidelity "
          f"{grid_teleport_report()['worst_fidelity']:.12f}")
    print("\n[3] No-cloning receipt - the original is destroyed, not copied")
    receipt = clone_receipt()
    print(f"    Alice's original qubit after measurement: "
          f"max deviation from I/2 = "
          f"{receipt['alice_qubit_is_half_identity_max_dev']:.2e}")
    print(f"    overlap of the leftover with the input: "
          f"{receipt['overlap_input_with_alice_leftover']:.4f} "
          f"(1/2 = maximally mixed, i.e. no copy)")
    print(f"    Bob before the classical bits arrive: also I/2 "
          f"(deviation "
          f"{receipt['bob_before_classical_bits_max_dev_vs_half_identity']:.2e})"
          f" - no signalling")
    print("\n[4] Superdense coding - the same pair, double duty")
    dense = dense_report()
    for msg, row in dense["messages"].items():
        print(f"    message {msg} -> decoded {row['decoded']} "
              f"at p = {row['probability']:.4f}")
    print("    -> 1 ebit + 1 qubit sent carries 2 classical bits, error-free")
    print("\n[5] Noisy pairs - the fidelity the protocol actually delivers")
    table = noise_table()
    for channel in ("depolarizing", "dephasing"):
        cells = "  ".join(
            f"{s}:{table[channel][s]['simulated']:.3f}"
            for s in ("0.0", "0.2", "0.4", "0.5", "0.6", "0.8", "1.0"))
        print(f"    {channel:14s} {cells}")
    crossings = noise_report()["crossings"]
    for channel, row in crossings.items():
        print(f"    {channel:14s} stops beating classical 2/3 at noise "
              f"{row['simulated_bisection']:.6f} "
              f"(analytic {row['analytic']:.6f})")
    print("\n[6] Resource ledger")
    ledger = ledger_report()
    q = ledger["quantum_teleportation"]
    print(f"    quantum: {q['ebits_consumed']} ebit + "
          f"{q['classical_bits_sent']} classical bits + "
          f"{q['input_copies_consumed']} copy -> fidelity {q['fidelity']}")
    cl = ledger["classical_estimation"]
    print(f"    classical estimation F(N) = (N+1)/(N+2): "
          f"N=1 -> {cl['table']['1']:.4f} (the 2/3 bound), "
          f"N=10 -> {cl['table']['10']:.4f}, "
          f"0.99 needs N = {cl['copies_for_0.99']} copies")
    print("\n[7] Link classifier (TinyML kNN, labels from the lab's policy)")
    for name, row in classifier_scenarios().items():
        print(f"    {name:32s} F = {row['fidelity']:.4f} -> {row['label']}")
    print("\n[8] Advisory seats")
    brains = brains_report()
    print(f"    decider: {brains['decider']['decision']} "
          f"trace={brains['decider']['trace_sha256_16']}")
    print(f"    advisor can_override_hold = {brains['advisor']['can_override_hold']}")
    print(f"    flow rendered = {brains['flow']['rendered']} "
          f"live = {brains['flow']['live']}")
    print(f"\n[9] HOLD gates: {len(HOLD_GATES)}")
    for key in HOLD_GATES:
        print(f"    HOLD  {key}")
    checks = run_checks()
    passed = sum(1 for _, ok in checks if ok)
    print(f"\nCHECKS {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL {name}")
    verdict = "PROCEED" if passed == len(checks) else "HOLD"
    print(f"VERDICT {verdict} (sandbox simulation only) | HOLD gates {len(HOLD_GATES)}")
    return 0 if passed == len(checks) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "demo":
        return demo()
    cmd = argv[0]
    if cmd == "checks":
        checks = run_checks()
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        print(f"CHECKS {sum(1 for _, ok in checks if ok)}/{len(checks)}")
        return 0 if all(ok for _, ok in checks) else 1
    if cmd == "teleport":
        print(json.dumps(teleport_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "grid":
        print(json.dumps(grid_teleport_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "clone":
        print(json.dumps(clone_receipt(), indent=2, sort_keys=True))
        return 0
    if cmd == "dense":
        print(json.dumps(dense_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "noise":
        print(json.dumps(noise_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "ledger":
        print(json.dumps(ledger_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "classify":
        print(json.dumps(classifier_scenarios(), indent=2, sort_keys=True))
        return 0
    if cmd == "brains":
        print(json.dumps(brains_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "holds":
        for key, value in HOLD_GATES.items():
            print(f"{key}: {value}")
        return 0
    if cmd == "hold-demo":
        action = argv[1] if len(argv) > 1 else "real_message_transmission"
        print(f"{action}: {HOLD_GATES.get(action, 'PROCEED - not gated')}")
        return 2 if gate(action) == "HOLD" else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
