class Nanger < Formula
  include Language::Python::Shebang

  desc "File manager and text editor in one (ranger + nano + vim)"
  homepage "https://github.com/Speederhun/Nanger"
  url "https://github.com/Speederhun/Nanger.git", tag: "v1.0.0"
  license "MIT"
  head "https://github.com/Speederhun/Nanger.git", branch: "main"

  depends_on "python"
  depends_on "pillow"
  depends_on "poppler"

  def install
    system "make", "install", "PREFIX=#{prefix}"
    rewrite_shebang python_shebang_rewrite_info(Formula["python"].opt_libexec/"bin/python"),
                    bin/"nanger"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/nanger --version")
  end
end
