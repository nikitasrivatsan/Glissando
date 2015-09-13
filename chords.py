#!/usr/bin/pypy

# set the path and import things
import sys
sys.path.append("/home/asrivat1/")
import music21
from music21 import *
from collections import defaultdict
import random
import math

# the N in n-gram
N1 = 2
N2 = 4

# the smoothing factor
# think of this as a measure of originality
lamb = 0.1

# modes that we see
keys = defaultdict(lambda: 0.0)

def trainDurations(score, durations, durvocab):
    oldDurations = ['<BOS>'] * N2

    for part in score.parts:
        for measure in part:
            if type(measure) == music21.stream.Measure:
                for component in measure:
                    if type(component) == music21.note.Note:
                        oldDurations.pop(0)
                        oldDurations.append(component.duration.type)

                        durgram = '\n'.join(oldDurations)
                        durations[durgram] += 1

                        durvocab.add(component.duration.type)


def parseFile(filename, ngrams, vocab, durations, durvocab):
    key = None
    mode = None
    score = corpus.parse(filename)

    # train durations on the notes, not the chords
    trainDurations(score, durations, durvocab)

    # next train chord ngrams on the chords
    chords = score.chordify().flat

    oldChords = ['<BOS>'] * N1

    for c in chords:
        if "Chord" in c.classes:
            root = c.root()
            relativeroot = str(interval.notesToChromatic(key, root).semitones)

            oldChords.pop(0)
            oldChords.append(relativeroot)

            ngram = '\n'.join(oldChords)
            ngrams[ngram] += 1

            relativePitches = []
            for p in c.pitchNames:
                relativePitches.append(str(interval.notesToChromatic(key, note.Note(p)).semitones))

            notes = " ".join(relativePitches) + '\t' + mode + '\t' + relativeroot

            vocab.add(notes)

        elif "KeySignature" in c.classes:
            key, mode = c.pitchAndMode
            if mode is None:
                mode = "unknown"
            keySignature = key.name + '\t' + mode
            keys[keySignature] += 1

def train(ngrams, vocab, durations, durvocab):
    #songs = corpus.getCorePaths('xml')
    songs = corpus.getBachChorales()
    for song in songs:
        parseFile(song, ngrams, vocab, durations, durvocab)

def sampleMultinomial(candidates, weights):
    point = random.random()
    total = 0.0
    for i in range(0, len(candidates)):
        total += weights[i]
        if total > point:
            return candidates[i]
    print "Error in sampling"

def sampleKey():
    candidates = []
    weights = []

    for k in keys:
        candidates.append(k)
        weights.append(keys[k])

    Z = sum(weights)
    weights = [x / Z for x in weights]

    return sampleMultinomial(candidates, weights)

def sampleDuration(durations, durvocab, quota, oldDurations):
    candidates = []
    weights = []

    for dur in durvocab:
        qlength = duration.convertTypeToQuarterLength(dur)
        if dur != "complex" and qlength <= quota and quota % qlength == 0:
            candidates.append(dur)
            durgram = '\n'.join(oldDurations) + '\n' + dur
            weights.append(durations[durgram])

    Z = sum(weights)
    weights = [x / Z for x in weights]

    return sampleMultinomial(candidates, weights)

def samplePitches(ngrams, vocab, oldChords, mode):
    candidates = []
    weights = []

    for c in vocab:
        if c.split('\t')[1] == mode:
            root = c.split('\t')[2]
            candidates.append(c)
            ngram = '\n'.join(oldChords) + '\n' + root
            weights.append(ngrams[ngram])

    if len(candidates) == 0:
        for c in vocab:
            candidates.append(c)
            weights.append(1.0)

    Z = sum(weights)
    weights = [x / Z for x in weights]

    return sampleMultinomial(candidates, weights)

def writeMelody(p, durations, durvocab, key, interv):
    melody = stream.Part()

    oldDurations = ["<BOS>"] * (N2 - 1)

    previous1 = note.Note(key)
    previous2 = note.Note(key)

    for hmeasure in p:
        hchord = hmeasure[0]
        pitches = hchord.pitches
        m = stream.Measure()

        quota = 4.0

        while quota > 0.0:
            # pick a duration
            dur = sampleDuration(durations, durvocab, quota, oldDurations)
            quota -= duration.convertTypeToQuarterLength(dur)

            # pick a pitch from the chord
            options = []
            for pitch in pitches:
                if not (previous2.name == pitch.name or previous1.name == pitch.name):
                    options.append(pitch)

            if len(options) == 0:
                for pitch in pitches:
                    options.append(interval.Interval(-12).transposePitch(pitch, maxAccidental = 1))
                    options.append(interval.Interval(12).transposePitch(pitch, maxAccidental = 1))

            penalty = []
            for pitch in options:
                penalty.append(math.fabs(float(interval.notesToChromatic(previous2, note.Note(pitch)).semitones)))

            mx = max(penalty)
            weights = [mx - x + 1 for x in penalty]
            Z = sum(weights)
            weights = [x / Z for x in weights]

            pitch = sampleMultinomial(options, weights)
            n = note.Note(pitch)

            # transpose for audibility
            n = n.transpose(interv)

            # add that note to measure
            n.duration.type = dur
            m.append(n)

            previous2 = previous1
            previous1 = n

        melody.append(m)

    return melody

def sampleRhythm(durations, durvocab, quota):
    oldDurations = ['<BOS>'] * (N2 - 1)
    pattern = []
    quota = 4.0

    while quota > 0.0:
        dur = sampleDuration(durations, durvocab, quota, oldDurations)
        quota -= duration.convertTypeToQuarterLength(dur)
        pattern.append(dur)

    return pattern

def writeSong(ngrams, vocab, durations, durvocab, timeSig):
    keySignature = sampleKey()
    key, mode = keySignature.split()

    s = stream.Score()
    p = stream.Part()

    # sample a rhythmic pattern
    pattern = sampleRhythm(durations, durvocab, 4.0)

    # first sample a harmonic baseline of one chord per measure

    oldChords = ['<BOS>'] * (N1 - 1)

    for i in range(0, 100):
        m = stream.Measure()
        c = samplePitches(ngrams, vocab, oldChords, mode)

        oldChords.pop(0)
        oldChords.append(c.split('\t')[2])
        
        # append the sampled chord to streams 
        absoluteNotes = [note.Note(key).transpose(int(j) - 12) for j in c.split('\t')[0].split()]
        toAdd = chord.Chord(absoluteNotes)
        toAdd.duration.type = "whole"
        
        m.append(toAdd)
        '''
        full = True
        for dur in pattern:
            toAdd = chord.Chord(absoluteNotes)
            if not full:
                toAdd = toAdd.root()
                full = False
            toAdd.duration.type = dur
            m.append(toAdd)
        '''

        # with some probability, modulate to the dominant or corresponding minor/major
        if random.random() > 0.8:
            key = interval.Interval('p5').transposePitch(music21.pitch.Pitch(key), maxAccidental = 1).name
        elif random.random() < 0.2:
            if mode == "major":
                key = interval.Interval('M3').transposePitch(music21.pitch.Pitch(key), maxAccidental = 1).name
                mode = "minor"
            else:
                key = interval.Interval('m3').transposePitch(music21.pitch.Pitch(key), maxAccidental = 1).name
                mode = "major"

        # every 8 measures, new rhythm
        if (i % 4) == 0:
            pattern = sampleRhythm(durations, durvocab, 4.0)

        p.append(m)

    s.append(p)

    # now sample a melody using the chords established
    melody = writeMelody(p, durations, durvocab, key, 24)

    s.append(melody)

    return s

def main():
    # stores the count for every ngram with add lambda smoothing
    ngrams = defaultdict(lambda: lamb)

    # stores the count for every rhythmic ngram with add lambda smoothing
    durations = defaultdict(lambda: lamb)

    # stores the full vocabulary of notes we've seen
    vocab = set()

    # stores all possible note durations
    durvocab = set()

    # train the ngrams and vocab
    print "Training on Entire Corpus"
    train(ngrams, vocab, durations, durvocab)
    print "Done training"

    # write a short song
    print "Writing a short song"
    s = writeSong(ngrams, vocab, durations, durvocab, 4.0)
    print "Done writing song"

    # write output to MIDI file
    print "Writing output to MIDI file"
    outfile = midi.translate.streamToMidiFile(s)
    outfile.open("/home/asrivat1/public_html/output.mid", 'wb')
    outfile.write()
    outfile.close()
    print "Done writing file"

if __name__ == "__main__":
    main()
