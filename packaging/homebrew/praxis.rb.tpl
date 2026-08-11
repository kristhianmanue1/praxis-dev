class Praxis < Formula
  desc "Executable governance for AI-assisted software projects"
  homepage "https://github.com/kristhianmanue1/praxis-dev"
  url "https://github.com/kristhianmanue1/praxis-dev/releases/download/v{{VERSION}}/praxis-{{VERSION}}.tar.gz"
  sha256 "{{SHA256}}"
  license "Apache-2.0"

  depends_on "python@3.12"

  def install
    libexec.install "praxis.pyz"
    python = Formula["python@3.12"].opt_bin/"python3.12"
    (bin/"praxis").write <<~SH
      #!/bin/bash
      exec "#{python}" -I "#{libexec}/praxis.pyz" "$@"
    SH
  end

  test do
    (testpath/"fixture").mkpath
    assert_match version.to_s, shell_output("#{bin}/praxis --version")
    assert_match "praxis/audit-result/v1", shell_output(
      "#{bin}/praxis project audit #{testpath}/fixture --format json", 1
    )
  end
end
