// OCR the bottom band of a video, frame by frame, with macOS Vision.
// Reads frames straight from the file, so nothing is written to disk.
//
// usage: swift ocr_frames.swift VIDEO [STEP] [TOP] [START] [END]
//   STEP   seconds between samples          (default 0.5)
//   TOP    crop from this fraction of height (default 0.82 = bottom 18%)
//   START  first second to sample            (default 0)
//   END    last second to sample             (default: whole video)
//
// Prints one line per recognised text box:
//   time <TAB> box-centre-x <TAB> box-width <TAB> confidence <TAB> text
// Box coordinates are fractions of the cropped band's width.

import AVFoundation
import CoreGraphics
import Foundation
import Vision

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("usage: ocr_frames.swift VIDEO [STEP] [TOP] [START] [END]\n".data(using: .utf8)!)
    exit(2)
}

let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
let step = args.count > 2 ? Double(args[2])! : 0.5
let top = args.count > 3 ? Double(args[3])! : 0.82
let start = args.count > 4 ? Double(args[4])! : 0
let duration = CMTimeGetSeconds(asset.duration)
let end = args.count > 5 ? min(Double(args[5])!, duration) : duration

let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
let tolerance = CMTime(seconds: 0.1, preferredTimescale: 600)
generator.requestedTimeToleranceBefore = tolerance
generator.requestedTimeToleranceAfter = tolerance

setvbuf(stdout, nil, _IOLBF, 0)

var t = start
while t < end {
    autoreleasepool {
        let at = CMTime(seconds: t, preferredTimescale: 600)
        guard let frame = try? generator.copyCGImage(at: at, actualTime: nil) else { return }
        let h = Double(frame.height)
        let band = CGRect(x: 0, y: h * top, width: Double(frame.width), height: h * (1 - top))
        guard let crop = frame.cropping(to: band) else { return }

        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hant", "zh-Hans"]
        request.usesLanguageCorrection = true
        try? VNImageRequestHandler(cgImage: crop, options: [:]).perform([request])

        for observation in request.results ?? [] {
            guard let best = observation.topCandidates(1).first else { continue }
            let box = observation.boundingBox
            print(String(format: "%.2f\t%.3f\t%.3f\t%.2f\t", t, box.midX, box.width, best.confidence) + best.string)
        }
    }
    t += step
}
