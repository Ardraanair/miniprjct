"""
blockchain.py
=============
Member 1 — Blockchain + Proof of Authority (PoA) Consensus

Core pipeline this file implements:
    Block -> Hash -> Previous Hash -> Blockchain -> Validation -> PoA

This module is self-contained: it can be imported by the Flask backend
(app.py) that another team member builds, or run directly for testing.
"""

import hashlib
import json
import time


# ---------------------------------------------------------------------------
# 1. BLOCK
# ---------------------------------------------------------------------------
class Block:
    """
    A single block in the chain.

    Fields:
        index        - position of the block in the chain (0 = genesis)
        timestamp    - when the block was created
        data         - the supply-chain transaction(s) stored in this block
                        e.g. {"product_id": "P1001", "event": "SHIPPED", ...}
        previous_hash- hash of the block before this one (this is what
                        actually "chains" the blocks together)
        validator    - which authority node (see PoA below) approved/created
                        this block
        hash         - this block's own hash, computed from everything above
    """

    def __init__(self, index, data, previous_hash, validator="genesis"):
        self.index = index
        self.timestamp = time.time()
        self.data = data
        self.previous_hash = previous_hash
        self.validator = validator
        self.hash = self.compute_hash()

    def compute_hash(self):
        """
        SHA-256 hash of the block's contents.

        We build a single JSON string from the block's fields (sorted keys
        so the string is always identical for identical data) and hash it.
        If ANY field changes later (even a single character in `data`),
        this hash will come out completely different -> tampering becomes
        detectable.
        """
        block_string = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "validator": self.validator,
        }, sort_keys=True)

        return hashlib.sha256(block_string.encode()).hexdigest()

    def to_dict(self):
        """Convert block to a plain dict — useful for Flask jsonify() and
        for storing/reading from Supabase."""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "validator": self.validator,
            "hash": self.hash,
        }

    def __repr__(self):
        return f"Block(#{self.index}, hash={self.hash[:10]}..., validator={self.validator})"


# ---------------------------------------------------------------------------
# 2. PROOF OF AUTHORITY (PoA) CONSENSUS
# ---------------------------------------------------------------------------
class ProofOfAuthority:
    """
    In PoA, instead of miners competing to solve puzzles (like Proof of
    Work), a fixed, pre-approved list of "authority" nodes takes turns
    creating blocks. This fits a supply-chain use case well: only trusted
    parties (e.g. Manufacturer, Distributor, Retailer, Regulator) should be
    allowed to add records to the chain.

    This class:
      - keeps the list of approved authorities
      - decides, in round-robin order, whose "turn" it is to validate
        (create) the next block
      - can approve/deny whether a given node is allowed to sign a block
    """

    def __init__(self, authorities):
        if not authorities:
            raise ValueError("PoA needs at least one authority node")
        self.authorities = list(authorities)
        self._turn = 0  # index into self.authorities

    def is_authority(self, node_name):
        return node_name in self.authorities

    def get_next_validator(self):
        """Round-robin: each authority takes turns producing blocks."""
        validator = self.authorities[self._turn % len(self.authorities)]
        self._turn += 1
        return validator

    def validate_block_authority(self, block):
        """A block is only legitimate if it was signed by a known authority."""
        return self.is_authority(block.validator)


# ---------------------------------------------------------------------------
# 3. BLOCKCHAIN
# ---------------------------------------------------------------------------
class Blockchain:
    def __init__(self, authorities):
        """
        authorities: list of trusted node names, e.g.
            ["Manufacturer", "Distributor", "Retailer"]
        """
        self.poa = ProofOfAuthority(authorities)
        self.chain = []
        self.pending_transactions = []
        self._create_genesis_block()

    # -- chain creation -----------------------------------------------------
    def _create_genesis_block(self):
        """The very first block. previous_hash is a fixed placeholder
        since there's no block before it."""
        genesis = Block(index=0, data={"message": "Genesis Block"},
                         previous_hash="0", validator="genesis")
        self.chain.append(genesis)

    def get_last_block(self):
        return self.chain[-1]

    # -- supply-chain transactions -------------------------------------
    def add_transaction(self, product_id, event, details=None):
        """
        Queue a supply-chain event to be included in the next block.
        event examples: "CREATED", "SHIPPED", "RECEIVED", "SOLD"
        """
        transaction = {
            "product_id": product_id,
            "event": event,
            "details": details or {},
            "time": time.time(),
        }
        self.pending_transactions.append(transaction)
        return transaction

    # -- PoA block creation --------------------------------------------
    def mine_block(self):
        """
        Take all pending transactions, get the next authority in the PoA
        rotation to "sign" them, and append a new block to the chain.
        """
        if not self.pending_transactions:
            raise ValueError("No pending transactions to add to a block")

        validator = self.poa.get_next_validator()

        new_block = Block(
            index=self.get_last_block().index + 1,
            data=self.pending_transactions,
            previous_hash=self.get_last_block().hash,
            validator=validator,
        )

        self.chain.append(new_block)
        self.pending_transactions = []  # clear queue
        return new_block

    # -- validation -------------------------------------------------------
    def is_chain_valid(self):
        """
        Walk the whole chain and check two things for every block after
        genesis:
          1. Hash integrity  - recomputing the block's hash right now
             gives the same value stored in block.hash (i.e. nobody
             edited the data after the fact).
          2. Link integrity  - block.previous_hash actually matches the
             hash of the block before it (i.e. the chain hasn't been
             reordered or spliced).
        Also checks that every block was signed by a real PoA authority.
        """
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            if current.hash != current.compute_hash():
                return False, f"Block {current.index} data has been tampered with"

            if current.previous_hash != previous.hash:
                return False, f"Block {current.index} is not linked to block {previous.index}"

            if not self.poa.validate_block_authority(current):
                return False, f"Block {current.index} was signed by an unauthorized node"

        return True, "Blockchain is valid"

    def print_chain(self):
        for block in self.chain:
            print(block)
            print(f"   data: {block.data}")
            print(f"   prev_hash: {block.previous_hash}")
            print(f"   hash:      {block.hash}")
            print("-" * 60)


# ---------------------------------------------------------------------------
# 4. DEMO / SELF-TEST  (run:  python blockchain.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Trusted authority nodes for this supply chain
    authorities = ["Manufacturer", "Distributor", "Retailer"]
    bc = Blockchain(authorities)

    # Simulate supply-chain events
    bc.add_transaction("P1001", "CREATED", {"location": "Factory A"})
    bc.mine_block()

    bc.add_transaction("P1001", "SHIPPED", {"from": "Factory A", "to": "Warehouse B"})
    bc.mine_block()

    bc.add_transaction("P1001", "RECEIVED", {"location": "Warehouse B"})
    bc.mine_block()

    print("=== BLOCKCHAIN ===")
    bc.print_chain()

    valid, msg = bc.is_chain_valid()
    print(f"\nValidation before tampering: {valid} - {msg}")

    # --- Tampering test ---
    print("\n--- Simulating tampering with block 1's data ---")
    bc.chain[1].data[0]["event"] = "STOLEN"  # attacker edits history directly

    valid, msg = bc.is_chain_valid()
    print(f"Validation after tampering:  {valid} - {msg}")
