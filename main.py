import pandas as pd
import numpy as np
import create_fingerprints as cf
import create_descriptors as cd
from rdkit import Chem
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV, train_test_split, cross_validate, RandomizedSearchCV
from sklearn.feature_selection import SelectKBest, f_classif, mutual_info_classif
from sklearn.metrics import classification_report, confusion_matrix, precision_score, recall_score, f1_score, \
    accuracy_score, roc_auc_score
from sklearn.preprocessing import scale
import matplotlib.pyplot as plt
import xgboost as xgb
from tqdm import tqdm


def create_original_df(write=False):
    # Create dataframe from csv
    df = pd.read_csv("./datasets/sider.csv")

    # Extract SMILES column
    df_molecules = pd.DataFrame(df["smiles"])

    # Converting to molecules
    df_molecules["mols"] = df_molecules["smiles"].apply(Chem.MolFromSmiles)

    # Droping mols and smiles
    df_y = df.drop("smiles", axis=1)

    # Write to csv
    if write:
        df_molecules.to_csv("./dataframes/df_molecules.csv")
        df_y.to_csv("./dataframes/df_y.csv")

    return df_y, df_molecules


def createfingerprints(df_mols, length):
    # Morgan Fingerprint (ECFP4)
    ecfp_df = cf.create_ecfp4_fingerprint(df_mols, length, False)

    # MACCS keys (always 167)
    maccs_df = cf.create_maccs_fingerprint(df_mols, False)

    # ATOM PAIRS
    atom_pairs_df = cf.create_atompairs_fingerprint(df_mols, length, False)

    # Topological torsion
    tt_df = cf.create_topological_torsion_fingerprint(df_mols, length, False)

    return ecfp_df, maccs_df, atom_pairs_df, tt_df


def createdescriptors(df_molecules):
    # Descriptors
    df_mols_desc = cd.calc_descriptors(df_molecules, False)

    return df_mols_desc


def test_fingerprint_size(df_mols, df_y, model, num_sizes_to_test=20, min_size=100, max_size=2048, cv=10,
                          makeplots=False,
                          write=False):
    # Fingerprint length type and selection
    # Scoring metrics to use
    scoring_metrics = ["roc_auc", "precision", "recall", "accuracy", "f1"]
    sizes = np.linspace(min_size, max_size, num_sizes_to_test, dtype=int)

    # Create results dataframes for each metric
    results_f1 = np.zeros([4, len(sizes)])
    results_rocauc = np.zeros([4, len(sizes)])
    results_precision = np.zeros([4, len(sizes)])
    results_recall = np.zeros([4, len(sizes)])
    results_accuracy = np.zeros([4, len(sizes)])

    # Get test sizes
    c = 0
    # Size testing using SVC with scale gamma (1 / (n_features * X.var()))
    for s in tqdm(sizes):
        # Create fingerprint with size S
        fingerprints = createfingerprints(df_mols, int(s))
        r = 0
        for fp in fingerprints:
            X = fp.copy()
            # Using "Hepatobiliary disorders" as an results example since its balanced
            y = df_y["Hepatobiliary disorders"].copy()
            # 10-fold cross validation
            cv_scores = cross_validate(model, X, y, cv=cv, scoring=scoring_metrics,
                                       return_train_score=False, n_jobs=-1)

            for k, v in cv_scores.items():
                if k == "test_roc_auc":
                    results_rocauc[r, c] = v.mean()
                if k == "test_precision":
                    results_precision[r, c] = v.mean()
                if k == "test_recall":
                    results_recall[r, c] = v.mean()
                if k == "test_accuracy":
                    results_accuracy[r, c] = v.mean()
                if k == "test_f1":
                    results_f1[r, c] = v.mean()
            r += 1
        c += 1

    all_results = (results_rocauc, results_precision, results_recall, results_accuracy, results_f1)

    # Create dataframe for results
    df_results_rocauc_size_SVC = pd.DataFrame(results_rocauc, columns=sizes)
    df_results_precision_size_SVC = pd.DataFrame(results_precision, columns=sizes)
    df_results_recall_size_SVC = pd.DataFrame(results_recall, columns=sizes)
    df_results_accuracy_size_SVC = pd.DataFrame(results_accuracy, columns=sizes)
    df_results_f1_size_SVC = pd.DataFrame(results_f1, columns=sizes)

    all_df_results = (
        df_results_rocauc_size_SVC, df_results_precision_size_SVC, df_results_recall_size_SVC,
        df_results_accuracy_size_SVC,
        df_results_f1_size_SVC)

    # Save to file
    if write:
        df_results_rocauc_size_SVC.to_csv("./results/df_results_rocauc_size_SVC.csv")
        df_results_precision_size_SVC.to_csv("./results/df_results_precision_size_SVC.csv")
        df_results_recall_size_SVC.to_csv("./results/df_results_recall_size_SVC.csv")
        df_results_accuracy_size_SVC.to_csv("./results/df_results_accuracy_size_SVC.csv")
        df_results_f1_size_SVC.to_csv("./results/df_results_f1_size_SVC.csv")

    if makeplots:
        fp_names = ["ECFP-4", "MACCS", "Atom Pairs", "Topological Torsion"]
        m = 0
        for d in all_results:
            fig = plt.figure(figsize=(10, 10))
            for i in range(len(fingerprints)):
                plt.plot(sizes, d[i, :], "-")
            plt.title(f"SVC, {scoring_metrics[m]} vs fingerprint length", fontsize=25)
            plt.ylabel(f"{scoring_metrics[m]}", fontsize=20)
            plt.xlabel("Fingerprint Length", fontsize=20)
            plt.legend(fp_names, fontsize=15)
            plt.ylim([0, 1])
            plt.show()
            m += 1

    return all_df_results


def select_best_descriptors(X, y, funcscore=f_classif, k=2):
    # Select k highest scoring feature from X to y with a score function, f_classif by defatult
    X_new = SelectKBest(score_func=funcscore, k=k).fit_transform(X, y)
    X_new_df = pd.DataFrame(X_new)
    return X_new_df


def grid_search(X_train, X_test, y_train, y_test, model, params_to_test, cv=10, scoring="f1", n_jobs=-1, verbose=False):
    # Define grid search
    grid_search = GridSearchCV(model, params_to_test, cv=cv, n_jobs=n_jobs, verbose=verbose, scoring=scoring)

    # Fit X and y to test parameters
    grid_search.fit(X_train, y_train)

    # Print scores
    print()
    print("Score for development set:")
    means = grid_search.cv_results_["mean_test_score"]
    stds = grid_search.cv_results_["std_test_score"]
    for mean, std, params in zip(means, stds, grid_search.cv_results_["params"]):
        print("%0.3f (+/-%0.03f) for %r" % (mean, std * 1.96, params))
    print()

    # Print best parameters
    print()
    print("Best parameters set found:")
    print(grid_search.best_params_)
    print()

    # Detailed Classification report
    print()
    print("Detailed classification report:")
    print("The model is trained on the full development set.")
    print("The scores are computed on the full evaluation set.")
    print()
    y_true, y_pred = y_test, grid_search.predict(X_test)
    print(classification_report(y_true, y_pred))
    print()
    print("Confusion Matrix as")
    print("""
    TN FP
    FN TP
    """)
    print(confusion_matrix(y_true, y_pred))
    # Save best estimator
    best_estimator = grid_search.best_estimator_
    # And return it
    return best_estimator


def random_search(X_train, X_test, y_train, y_test, model, grid, n_iter=100, cv=10, scoring="f1", n_jobs=-1,
                  verbose=False):
    # Define random search
    rs = RandomizedSearchCV(model, grid, n_iter=n_iter, cv=cv, scoring=scoring, n_jobs=n_jobs, verbose=verbose)

    # Fit parameters
    rs.fit(X_train, y_train)

    # Print scores
    print()
    print("Score for development set:")
    means = rs.cv_results_["mean_test_score"]
    stds = rs.cv_results_["std_test_score"]
    for mean, std, params in zip(means, stds, rs.cv_results_["params"]):
        print("%0.3f (+/-%0.03f) for %r" % (mean, std * 1.96, params))
    print()

    # Print best parameters
    print()
    print("Best parameters set found:")
    print(rs.best_params_)
    print()

    # Detailed Classification report
    print()
    print("Detailed classification report:")
    print("The model is trained on the full development set.")
    print("The scores are computed on the full evaluation set.")
    print()
    y_true, y_pred = y_test, rs.predict(X_test)
    print(classification_report(y_true, y_pred))
    print()
    print("Confusion Matrix as")
    print("""
       TN FP
       FN TP
       """)
    print(confusion_matrix(y_true, y_pred))
    # Save best estimator
    best_estimator = rs.best_estimator_
    # And return it
    return best_estimator


def score_report(estimator, X_test, y_test):
    # Predicting value
    y_true, y_pred = y_test, estimator.predict(X_test)

    # Detailed Classification report
    print()
    print("The scores are computed on the full evaluation set")
    print("These are not used to train or optimize the model")
    print()
    print("Detailed classification report:")
    print(classification_report(y_true, y_pred))
    print()
    print("Confusion matrix as:")
    print("""
           TN FP
           FN TP
           """)
    print(confusion_matrix(y_true, y_pred))
    print()

    # Individual metrics
    f1 = f1_score(y_true, y_pred)
    auc = roc_auc_score(y_true, y_pred)
    rec = recall_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred)
    acc = accuracy_score(y_true, y_pred)

    print("Individual metrics:")
    print(f"F1 score: {f1:.2f}")
    print(f"ROC-AUC score: {auc:.2f}")
    print(f"Recall score: {rec:.2f}")
    print(f"Precision score: {prec:.2f}")
    print(f"Accuracy score: {acc:.2f}")
    print()


def cv_report(estimator, X_train, y_train, cv=10, scoring_metrics=("f1", "roc_auc", "recall", "precision", "accuracy"),
              n_jobs=-1, verbose=False):
    # Cross validation
    scores = cross_validate(estimator, X_train, y_train, scoring=scoring_metrics, cv=cv, n_jobs=n_jobs, verbose=verbose,
                            return_train_score=False)

    # Means
    f1_s = np.mean(scores["test_f1"])
    auc_s = np.mean(scores["test_roc_auc"])
    rec_s = np.mean(scores["test_recall"])
    prec_s = np.mean(scores["test_precision"])
    acc_s = np.mean(scores["test_accuracy"])

    # STD
    f1_std = np.std(scores["test_f1"])
    auc_std = np.std(scores["test_roc_auc"])
    rec_std = np.std(scores["test_recall"])
    prec_std = np.std(scores["test_precision"])
    acc_std = np.std(scores["test_accuracy"])

    print()
    print("Individual metrics")
    print(f"F1 Score: Mean: {f1_s:.2f} (Std: {f1_std:.2})")
    print(f"ROC-AUC score: Mean: {auc_s:.2f} (Std: {auc_std:.2})")
    print(f"Recall score: Mean: {rec_s:.2f} (Std: {rec_std:.2})")
    print(f"Precision score: Mean: {prec_s:.2f} (Std: {prec_std:.2})")
    print(f"Accuracy score: Mean: {acc_s:.2f} (Std: {acc_std:.2})")
    print()


# Process
# Fixing the seed
seed = 6
np.random.seed(seed)

# Creating base df_molecules, df_y with the results vectors, and df_mols_descr with the descriptors
df_y, df_molecules = create_original_df(write=False)
df_molecules.drop("smiles", axis=1, inplace=True)

# Machine learning process
# Separating in a DF_mols_train and an Df_mols_test, in order to avoid data snooping and fitting the model to the test
df_mols_train, df_mols_test, all_y_train, all_y_test = train_test_split(df_molecules, df_y, test_size=0.2,
                                                                        random_state=seed)

# Fingerprint length
# all_df_results_svc = test_fingerprint_size(df_mols_train, all_y_train, SVC(gamma="scale", random_state=seed),
#                                            makeplots=True, write=True)
# Best result with ECFP-4 at 1125


# Creating dataframes
print("Creating dataframes")
X_all, _, _, _ = createfingerprints(df_molecules, length=1125)
X_train, _, _, _ = createfingerprints(df_mols_train, length=1125)
X_test, _, _, _ = createfingerprints(df_mols_test, length=1125)
y_all = df_y["Hepatobiliary disorders"].copy()
y_train = all_y_train["Hepatobiliary disorders"].copy()
y_test = all_y_test["Hepatobiliary disorders"].copy()
df_desc = createdescriptors(df_molecules)

X_descriptors = select_best_descriptors(df_desc, y_all, funcscore=f_classif, k=4)
df_desc_train, df_desc_test = train_test_split(X_descriptors, test_size=0.2, random_state=seed)

X_train = pd.concat([X_train, df_desc_train], axis=1)
X_test = pd.concat([X_test, df_desc_test], axis=1)

# SVC
print()
print("Base SVC:")
base_svc = SVC(gamma="auto", random_state=seed)
base_svc.fit(X_train, y_train)
score_report(base_svc, X_test, y_test)

# Test SVC parameters
# print("Test best SVC")
# params_to_test = {"kernel": ["linear", "rbf"], "C": [1, 10, 100], "gamma": [1, 0.1, 0.001]}
# best_svc = grid_search(X_train, X_test, y_train, y_test, SVC(random_state=seed), params_to_test, cv=10, scoring="f1", verbose=True, n_jobs=-2)
# {'C': 10, 'gamma': 0.1, 'kernel': 'rbf'}

print()
print("Improved SVC Parameters")
impr_svc = SVC(C=10, kernel="rbf", gamma=0.1, random_state=seed)
impr_svc.fit(X_train, y_train)
score_report(impr_svc, X_test, y_test)

# Test RF
# print("Test best RF")
# n_estimators = [int(x) for x in np.linspace(750, 850, 6, dtype=int)]
n_estimators = [820, 830, 840]
max_features = ["log2", "sqrt"]
# max_depth = [int(x) for x in np.linspace(100, 180, 8, dtype=int)]
max_depth = [90, 100, 110]
min_samples_split = [11, 12, 13]
min_samples_leaf = [1, 2]
bootstrap = [True]

random_grid = {'n_estimators': n_estimators,
               'max_features': max_features,
               'max_depth': max_depth,
               'min_samples_split': min_samples_split,
               'min_samples_leaf': min_samples_leaf,
               'bootstrap': bootstrap}

# best_random_rf = random_search(X_train, X_test, y_train, y_test, RandomForestClassifier(random_state=seed), grid=random_grid, n_iter=300, cv=3, scoring="f1", n_jobs=-2, verbose=True)


# best_rf = grid_search(X_train, X_test, y_train, y_test, RandomForestClassifier(random_state=seed), random_grid, cv=3, scoring="f1", n_jobs=-2, verbose=True)
# 6th {'bootstrap': True, 'max_depth': 100, 'max_features': 'log2', 'min_samples_leaf': 1, 'min_samples_split': 12, 'n_estimators': 830}

# Test XGbBoost

xgb_model = xgb.XGBClassifier(objective="binary:logistic", random_state=seed)
xgb_model.fit(X_train, y_train)
y_pred = xgb_model.predict(X_test)
print(confusion_matrix(y_test, y_pred))
print(f1_score(y_test, y_pred))
