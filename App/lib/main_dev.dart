import 'app/bootstrap.dart';
import 'data/repositories/fake_moisture_repository.dart';

/// Dev flavor: the in-memory fake backend with sample plants, devices and users (App/specs.md Part A §14).
/// Signed in as `demo`; sign out and in again with `demo` / `demo`, `anna` / `anna` or `ben` / `ben`.
void main() => bootstrap(FakeMoistureRepository());
