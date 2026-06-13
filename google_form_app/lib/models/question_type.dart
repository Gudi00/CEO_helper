/// The three Google Forms question kinds this app supports.
///
/// Wire values (`single_choice` / `multiple_choice` / `text_input`) are kept
/// identical to the JSON the injected parser and the Gemini prompts use, so
/// the strings round-trip without translation.
enum QuestionType {
  singleChoice('single_choice'),
  multipleChoice('multiple_choice'),
  textInput('text_input');

  const QuestionType(this.wire);

  /// The canonical string used in JSON / prompts / question hashes.
  final String wire;

  static QuestionType fromWire(String value) {
    return QuestionType.values.firstWhere(
      (t) => t.wire == value,
      orElse: () => throw ArgumentError('Unknown question type: $value'),
    );
  }

  bool get isChoice =>
      this == QuestionType.singleChoice || this == QuestionType.multipleChoice;
}
