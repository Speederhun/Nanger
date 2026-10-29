class Nanger < Formula
  include Language::Python::Shebang

  desc "File manager and text editor in one (ranger + nano + vim)"
  homepage "https://github.com/Speederhun/Nanger"
  url "https://github.com/Speederhun/Nanger.git", tag: "v1.8.0"
  license "MIT"
  head "https://github.com/Speederhun/Nanger.git", branch: "main"

  depends_on "python@3.13"
  depends_on "pillow"
  depends_on "poppler"

  def install
    system "make", "install", "PREFIX=#{prefix}"
    rewrite_shebang python_shebang_rewrite_info(Formula["python@3.13"].opt_bin/"python3.13"),
                    bin/"nanger"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/nanger --version")
  end
end
