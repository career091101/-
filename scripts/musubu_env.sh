# Musubu shell scripts: human-readable timestamps in Tokyo (JST).
export TZ=Asia/Tokyo

musubu_now() {
  date -Is
}
