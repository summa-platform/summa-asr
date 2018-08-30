from math import *


# Python 3 compatible version
def fst_shortest_path_to_lists(fst_shortest):
    """Converts openfst lattice produced by n-shortest path algorithm to n lists of output labels.

    Args:
        fst_shortest(fst.StdVectorFst): result of shortest_path algorithm

    Returns:
        list of pairs (path_weight, [path])
    """

    # There are n - eps arcs from 0 state which mark beginning of each list
    # Following one path there are 2 eps arcs at beginning
    # and one at the end before final state
    first_arcs, word_ids = [], []
    if len(fst_shortest) > 0:
        first_arcs = [a for a in fst_shortest[0].arcs]
    for arc in first_arcs:
        # first arc is epsilon arc
        assert(arc.ilabel == 0 and arc.olabel == 0)
        arc = next(fst_shortest[arc.nextstate].arcs)
        # second arc is also epsilon arc
        assert(arc.ilabel == 0 and arc.olabel == 0)
        # assuming logarithmic semiring
        path, weight = [], 0
        # start with third arc
        arc = next(fst_shortest[arc.nextstate].arcs)
        try:
            while arc.olabel != 0:
                path.append(arc.olabel)
                weight += float(arc.weight)  # TODO use the Weights plus operation explicitly
                arc = next(fst_shortest[arc.nextstate].arcs)
            weight += float(arc.weight)
        except StopIteration:
            pass

        word_ids.append((float(weight), path))
    word_ids.sort()
    return word_ids

# Patch for Python 3 compatibility
import alex_asr.utils
alex_asr.utils.fst_shortest_path_to_lists = fst_shortest_path_to_lists


def create_asr(model="model"):
    from alex_asr.utils import lattice_to_nbest
    from alex_asr import Decoder

    recogniser = Decoder(model)
    return ASR(recogniser, lattice_to_nbest)

class ASR:

    def __init__(self, recogniser, lattice_to_nbest):
        self.recogniser = recogniser
        self.lattice_to_nbest = lattice_to_nbest
        self.decoded_frames = 0
        self.callbacks = []

    def recognize_chunk(self, chunk):
        self.recogniser.accept_audio(chunk)
        self.recogniser.input_finished()

        while True:
            dec_t = self.recogniser.decode(max_frames=100)
            self.decoded_frames += dec_t

            if dec_t == 0:
                return

    def get_one_best_path(self):
        if self.decoded_frames == 0:
            return (1.0, '')
        else:
            p, interim_result = self.recogniser.get_best_path()
            return p, self._tokens_to_words(interim_result)

    def _tokens_to_words(self, tokens):
        return " ".join([self.recogniser.get_word(x).decode('utf8') for x in tokens])

    def get_final_hypothesis(self, compute_alignment=False, compute_alignment_with_word_confidence=False):
        if self.decoded_frames == 0:
            return [(1.0, '')], [], []

        self.recogniser.finalize_decoding()
        utt_lik, lat = self.recogniser.get_lattice()
        alignment = self.get_alignment() if compute_alignment else None
        alignment_with_confidence = self.get_alignment_with_word_confidence() if compute_alignment_with_word_confidence else None
        self.reset()

        return self._to_nbest(lat, 10), alignment, alignment_with_confidence

    def get_alignment(self):
        if self.decoded_frames == 0:
            return []

        alignment = self.recogniser.get_time_alignment()
        return [(self.recogniser.get_word(w).decode('utf8'), t, d) for (w,t,d) in zip(*alignment)]

    def get_alignment_with_word_confidence(self):
        if self.decoded_frames == 0:
            return []

        alignment = self.recogniser.get_time_alignment_with_word_confidence()
        return [(self.recogniser.get_word(w).decode('utf8'), t, d, c) for (w,t,d,c) in zip(*alignment)]

    def _to_nbest(self, lattice, n):
        return [(exp(-prob), self._tokens_to_words(path)) for (prob, path) in self.lattice_to_nbest(lattice, n=n)]

    def reset(self):
        self.decoded_frames = 0
        self.recogniser.reset()
