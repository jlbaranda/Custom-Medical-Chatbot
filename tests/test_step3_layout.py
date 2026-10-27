"""The Step 3 formatter must not weaken citation/grounding/safety checks."""
from guardrails.output_check import check_output, render
from guardrails.types import Passage

DOC = Passage('a', 'Asthma is a respiratory condition. Asthma can cause coughing. '
              'Symptoms include wheezing and coughing. Cold air can trigger asthma. '
              'Pollen can also trigger asthma.',
              'Asthma', 'MedlinePlus', 'https://medlineplus.gov/asthma.html', 12.0)
CFG = {'output': {'require_citations': True, 'min_support': 0.5,
                  'block_doses_in': ['answer', 'redirect']}}


def test_single_survivor_from_bullet_list_renders_as_paragraph():
    draft = ('Asthma is a respiratory condition. [1]\n\n'
             '- Jupiter has purple mountains and icy rivers. [1]\n'
             '- **Cold air:** Cold air can trigger asthma. [1]\n'
             '- Mercury is full of orange mountains and rivers. [1]')
    checked = check_output(draft, [DOC], CFG, 'answer')
    text, sources = render(checked, [DOC])
    assert checked.dropped.get('unsupported') == 2
    assert '**Cold air:** Cold air can trigger asthma. [1]' in text
    assert '\n\n**Cold air:**' in text
    assert '\n- **Cold air:**' not in text
    assert sources == [DOC]


def test_two_bullets_keep_a_readable_list_and_dedupe_citations():
    draft = ('- **Coughing:** Asthma can cause coughing. [1]\n'
             '- **Wheezing:** Symptoms include wheezing and coughing. [1]')
    checked = check_output(draft, [DOC], CFG, 'answer')
    body, _ = render(checked, [DOC])
    assert body.startswith('- **Coughing:**')
    assert '\n- **Wheezing:**' in body


def test_uncited_and_unsupported_medical_bullets_still_dropped():
    draft = ('- Asthma can cause coughing.\n'
             '- Jupiter causes asthma symptoms in everyone. [1]\n'
             '- Asthma is a respiratory condition. [1]')
    checked = check_output(draft, [DOC], CFG, 'answer')
    assert checked.dropped == {'uncited': 1, 'unsupported': 1}
    assert len(checked.kept) == 1


def test_dose_and_personalized_diagnosis_still_blocked():
    medication = Passage('b', 'Take 500 mg of medication each day. You likely have asthma.',
                         'Med', 'NIH', 'https://example.org/med', 15)
    checked = check_output('- Take 500 mg of medication each day. [1]\n'
                           '- You likely have asthma. [1]', [medication], CFG, 'answer')
    assert checked.dropped.get('dose') == 1
    assert checked.dropped.get('personal_claim') == 1
    assert not checked.kept
