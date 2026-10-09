import 'app/bootstrap.dart';
import 'data/repositories/fake_moisture_repository.dart';

/// Dev flavor. Runs against the in-memory fake backend until the real API
/// client exists (App/specs.md Part A §14).
void main() => bootstrap(FakeMoistureRepository());
