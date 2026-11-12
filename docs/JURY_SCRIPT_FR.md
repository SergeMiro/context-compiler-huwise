# Script de démonstration — 6 minutes

Page : <https://context.smiro.dev/> (mode « Technique »). Tous les chiffres viennent des runs enregistrés
affichés sur la page ; rien n'est tapé à la main. Runs du 11–12.11.2026, modèle gratuit
`nvidia/nemotron-3.5-super-vl:free`, un run par configuration.

## 0:00 — La thèse (20 s)

« Nous ne remplaçons pas Huwise. Nous proposons une boucle de mesure et d'optimisation sûre, au-dessus de ses
outils existants. Trois choses : je montre que je comprends votre architecture, je propose deux couches, et je
montre des mesures reproductibles — avec leurs limites. »

## 0:20 — Écran 1 : Huwise aujourd'hui (70 s)

- Mode **Huwise aujourd'hui**. « Chaque bloc a un statut. Vert = confirmé par votre documentation publique ; je
  clique sur *Huwise MCP Server* : quatre outils — analyze_catalog, search_assets, get_asset,
  search_asset_records — avec la citation et le lien. »
- Cliquer *Living Context Layer* : « les signaux que vous documentez : recherches, y compris sans résultat, vues,
  exports, demandes d'accès, actions des agents via MCP. »
- Cliquer *Stockage publié / index* (jaune) : « ici je ne sais pas comment c'est fait chez vous, donc je ne
  l'affirme pas : INFERRED. »
- Les traits : « métadonnées, schéma, requête de données, retour d'usage, gouvernance — ce ne sont pas les mêmes
  flux. »

## 1:30 — Écran 2 : nos deux couches (50 s)

- Mode **Avec nos couches**. Les blocs Huwise ne bougent pas ; deux blocs violets apparaissent.
- *Context Optimizer* : « le contexte de chaque requête : fiches compilées, recettes vérifiées, valeurs ancrées,
  routeur FAST/STANDARD/DEEP, cache, contrat de preuve. Aucun modèle sur le chemin chaud. »
- *AutoContext Lab* : « les expériences, uniquement en preprod, une modification à la fois, et la mise en
  production reste une décision humaine. »

## 2:20 — Écran 3 : une question tracée (70 s)

- Scénario « Le cas principal », configuration **C**, *Rejouer* : route FAST → une requête Explore API →
  vérification. « 23 collèges à Dijon, zéro appel au modèle, la preuve est le total_count de l'API. »
- *Lancer en direct* : badge **LIVE**, l'appel part maintenant — pour la version choisie (A, 0, B ou C).
- Sélecteur **Modèle** : OpenRouter (`nemotron-3.5-super-vl`) ou NVIDIA NIM (`nemotron-3-ultra-550b`). « Deux
  fournisseurs, deux quotas : si l'un est à sa limite, l'autre prend le relais, et la page affiche qui a répondu. »
- Basculer sur **A** : « même question, même modèle, mais avec votre vrai serveur Huwise MCP — ses quatre outils,
  tels que `tools/list` les renvoie. Il trouve aussi 23, en 4 appels au modèle et 11 secondes. »
- Précision honnête : « A, c'est votre serveur MCP avec la clé d'un compte utilisateur ordinaire, piloté par mon
  modèle gratuit et mon prompt. Ce n'est pas Huwy : je n'ai ni votre modèle ni votre prompt. »

## 3:30 — Écran 4 : une erreur observée (40 s)

- *Rejouer la requête* sur `code_departement='21'` : 0 ligne, `'021'` : 74. « Ce n'est pas une erreur de Huwy,
  c'est un piège de format que tout agent rencontre. L'Optimizer répond par un indice : *codes are written with
  leading zeros, try '021'*. »

## 4:10 — Écran 5 : AutoResearch en preprod (50 s)

- Le cycle en 10 étapes, le budget, le quality gate fixé avant le run.
- Le journal : diagnostic des échecs, la modification proposée (diff), la décision gardée ou annulée, la chaîne
  sha256 intacte. « Le lab ne voit jamais le holdout et ne peut toucher ni l'évaluateur ni les réponses attendues. »
- Le run de cette nuit : trois modifications essayées, **trois annulées**. Une corrigeait une question mais en
  cassait une de contrôle. « Le quality gate a fait son travail : rien n'est passé. »

## 5:00 — Écran 6 : la comparaison (50 s)

- Jeu **holdout**, 26 questions que le lab n'a jamais vues. Réponses justes : A (votre serveur MCP) **50 %**,
  B (fiches) **73 %**, C (fiches + Optimizer) **96 %**. *Faux et affirmé* : 12, 7, 1. Appels modèle : 136, 126, 56.
- « B contre A : +23 points, mais l'intervalle de confiance va de −4 à +50 : sur 26 questions, ce n'est pas
  significatif. C contre A : +46 points, intervalle de +23 à +65, p = 0,002. »
- « Les limites : 26 questions, un modèle gratuit, un run par configuration, et des questions écrites par moi —
  la moitié passe par une recette FAST, c'est un plafond. Je ne dis pas que c'est mieux que Huwy : je dis que la
  boucle mesure, au-dessus de vos outils. »

## 5:50 — Clôture (10 s)

« Les expériences tournent en preprod, base et index séparés ; la prod ne reçoit qu'une version vérifiée, sur
décision humaine. Ce que je vous propose, c'est de brancher cette boucle sur vos outils, avec vos signaux
d'usage. »

## Questions probables

- *Pourquoi pas de vecteurs ?* — Le classement BM25 + signal d'usage met le bon jeu en tête sur ce portail ; on
  ajoute des vecteurs quand l'éval montre que le rappel est le goulot.
- *Que se passe-t-il si le schéma change ?* — Écran 3, scénario « Le schéma a changé » (simulé) : la recette se
  désactive, la question repart par l'agent ; le cache change de clé avec la version de données.
- *Et les droits ?* — La clé du client est transmise, jamais stockée ; le cache est séparé par périmètre de droits
  (HMAC de la clé) ; un 403 donne un refus, pas un nombre (scénario « Jeu de données non autorisé »).
