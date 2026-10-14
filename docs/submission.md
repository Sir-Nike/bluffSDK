# Submission

The event submission is a Linux/amd64 Docker image identified by its immutable
repository@sha256 digest. Follow [the runtime image contract](docker-submission.md).
Include the SDK agent, pinned dependencies, packaged model weights (if used),
exec-form ENTRYPOINT, required resource labels, and USER 10000:10000 in that
image. Runtime networking/downloads are unavailable. Source provenance and
submission.json may accompany the image for documentation; runtime allocation
uses inspected image labels. Registration/intake is outside this runtime's scope.
