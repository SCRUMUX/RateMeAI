import { useState } from 'react';
import NavBar from '../sections/NavBar';
import Hero from '../sections/Hero';
import HowItWorks from '../sections/HowItWorks';
import Simulation from '../sections/Simulation';
import AppScreen from '../sections/AppScreen';
import Pricing from '../sections/Pricing';
import Footer from '../sections/Footer';
import AuthModal from '../components/AuthModal';
import MeshGradientBg from '../components/effects/MeshGradientBg';
import EnergyField from '../components/effects/EnergyField';
import { useApp } from '../context/AppContext';

export default function Landing() {
  const app = useApp();
  const [authModalOpen, setAuthModalOpen] = useState(false);

  return (
    <div data-category={app.activeCategory} className="min-h-screen w-full overflow-x-hidden selection:bg-brand-primary/30">
      <NavBar onLoginClick={() => setAuthModalOpen(true)} />
      <main className="relative">
        <MeshGradientBg />
        <EnergyField />
        <Hero />
        <HowItWorks />
        <Simulation />
        <AppScreen onOpenAuthModal={() => setAuthModalOpen(true)} />
        <Pricing />
      </main>
      <Footer />

      <AuthModal
        open={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onAuth={async (email) => {
          await app.authenticateUser(email);
          setAuthModalOpen(false);
        }}
        onOAuth={async (provider) => {
          await app.loginWithOAuth(provider);
        }}
        onPhoneLogin={async (token, userId) => {
          await app.loginWithToken(token, userId, 'phone');
          setAuthModalOpen(false);
        }}
      />
    </div>
  );
}
