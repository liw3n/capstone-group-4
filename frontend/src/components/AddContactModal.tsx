import { useState } from 'react';
import { Contact } from '../types';
import { isValidEmail } from '../lib/email';
import Modal, { ModalRow } from '../ui/Modal';
import Button from '../ui/Button';

interface AddContactModalProps {
  onClose: () => void;
  onSave: (contact: Omit<Contact, 'id'>) => void;
}

/** Common dialling codes; the field stays free-text for anything else. */
const COUNTRY_CODES = ['+65', '+60', '+62', '+66', '+63', '+84', '+852', '+86', '+91', '+61', '+44', '+1'];

export default function AddContactModal({ onClose, onSave }: AddContactModalProps) {
  const [name, setName] = useState('');
  const [dob, setDob] = useState('');
  const [nric, setNric] = useState('');
  const [email, setEmail] = useState('');
  const [countryCode, setCountryCode] = useState('+65');
  const [phone, setPhone] = useState('');
  const [touched, setTouched] = useState(false);

  const errors = {
    name: !name.trim() ? 'Name is required.' : '',
    email: !email.trim()
      ? 'Email is required.'
      : !isValidEmail(email)
        ? 'Enter a valid email address.'
        : '',
    phone: !phone.trim() ? 'Phone number is required.' : '',
  };

  const isValid = !errors.name && !errors.email && !errors.phone;

  const handleSave = () => {
    setTouched(true);
    if (!isValid) return;

    onSave({
      name: name.trim(),
      email: email.trim(),
      countryCode,
      phone: phone.trim().replace(/[\s-]/g, ''),
      dob: dob || undefined,
      nric: nric.trim() || undefined,
      // New contacts start as prospects until the advisor promotes them.
      label: 'Prospect',
      // Entered by hand, so this is the advisor's own contact by definition.
      source: 'own',
    });
  };

  const errorFor = (key: keyof typeof errors) =>
    touched && errors[key] ? (
      <p className="mt-1 text-[11px] text-danger">{errors[key]}</p>
    ) : null;

  return (
    <Modal
      title="Add Contact"
      onClose={onClose}
      width="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            CANCEL
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={touched && !isValid}>
            SAVE
          </Button>
        </>
      }
    >
      <div className="flex flex-col">
        <ModalRow label="Name *">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Full name"
            className="input-field"
            autoFocus
          />
          {errorFor('name')}
        </ModalRow>

        <ModalRow label="Date of Birth">
          <input
            type="date"
            value={dob}
            onChange={(e) => setDob(e.target.value)}
            className="input-field"
          />
        </ModalRow>

        <ModalRow label="NRIC">
          <input
            value={nric}
            onChange={(e) => setNric(e.target.value)}
            placeholder="NRIC or passport number"
            className="input-field"
          />
        </ModalRow>

        <ModalRow label="Email *">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@example.com"
            className="input-field"
          />
          {errorFor('email')}
        </ModalRow>

        <ModalRow label="Phone *">
          <div className="flex items-center gap-2">
            <input
              list="country-codes"
              value={countryCode}
              onChange={(e) => setCountryCode(e.target.value)}
              className="input-field w-24 shrink-0"
              aria-label="Country code"
            />
            <datalist id="country-codes">
              {COUNTRY_CODES.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="91234567"
              className="input-field"
              aria-label="Phone number"
            />
          </div>
          {errorFor('phone')}
        </ModalRow>
      </div>
    </Modal>
  );
}
